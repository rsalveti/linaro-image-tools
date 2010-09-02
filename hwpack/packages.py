import os
import shutil
import tempfile

from apt.cache import Cache
from apt.package import FetchError
import apt_pkg


class DummyProgress(object):

    def start(self):
        pass

    def ims_hit(self, item):
        pass

    def fail(self, item):
        pass

    def fetch(self, item):
        pass

    def pulse(self, owner):
        return True

    def media_change(self):
        return False

    def stop(self):
        pass


class FetchedPackage(object):
    """The result of fetching packages.

    :ivar name: the name of the fetched package.
    :type name: str
    :ivar version: the version of the fetched package.
    :type version: str
    :ivar filename: the filename that the package has.
    :type filename: str
    :ivar content: a file that the content of the package can be read from.
    :type content: a file-like object
    :ivar size: the size of the package
    :type size: int
    :ivar md5: the hex representation of the md5sum of the contents of
        the package.
    :type md5: str
    """

    def __init__(self, name, version, filename, content, size, md5):
        """Create a FetchedPackage.

        See the instance variables for the arguments.
        """
        self.name = name
        self.version = version
        self.filename = filename
        self.content = content
        self.size = size
        self.md5 = md5

    def __eq__(self, other):
        return (self.name == other.name
                and self.version == other.version
                and self.filename == other.filename
                and self.content.read() == other.content.read()
                and self.size == other.size
                and self.md5 == other.md5)

    def __hash__(self):
        return hash(
            (self.name, self.version, self.filename, self.size, self.md5))


class PackageFetcher(object):
    """A class to fetch packages from a defined list of sources."""

    def __init__(self, sources):
        """Create a PackageFetcher.

        Once created a PackageFetcher should have its `prepare` method
        called before use.

        :param sources: a list of sources such that they can be prefixed
            with "deb " and fed to apt.
        :type sources: an iterable of str
        """
        self.sources = sources
        self.tempdir = None

    def prepare(self):
        """Prepare a PackageFetcher for use.

        Should be called before use, and after any modification to the list
        of sources.
        """
        self.cleanup()
        self.tempdir = tempfile.mkdtemp(prefix="hwpack-apt-cache-")
        files = ["var/lib/dpkg/status",
                ]
        dirs = ["var/lib/dpkg",
                "etc/apt/",
                "var/cache/apt/archives/partial",
                "var/lib/apt/lists/partial",
               ]
        for d in dirs:
            os.makedirs(os.path.join(self.tempdir, d))
        for fn in files:
            with open(os.path.join(self.tempdir, fn), 'w'):
                pass
        sources_list = os.path.join(
            self.tempdir, "etc", "apt", "sources.list")
        with open(sources_list, 'w') as f:
            for source in self.sources:
                f.write("deb %s\n" % source)
        self.cache = Cache(rootdir=self.tempdir, memonly=True)
        self.cache.update()
        self.cache.open()

    def cleanup(self):
        """Cleanup any remaining artefacts.

        Should be called on all PackageFetchers when they are finished
        with.
        """
        if self.tempdir is not None and os.path.exists(self.tempdir):
            shutil.rmtree(self.tempdir)

    def fetch_packages(self, packages):
        """Fetch the files for the given list of package names.

        :param packages: a list of package names to install
        :type packages: an iterable of str
        :return: a dict containing the filenames of the .debs that were
            fetched as the keys, and file objects with the contents of
            those debs as the values.
        :rtype: a dict mapping str to file-like objects.
        :raises KeyError: if any of the package names in the list couldn't
            be found.
        """
        results = []
        for package in packages:
            candidate = self.cache[package].candidate
            base = os.path.basename(candidate.filename)
            destfile = os.path.join(self.tempdir, base)
            acq = apt_pkg.Acquire(DummyProgress())
            acqfile = apt_pkg.AcquireFile(
                acq, candidate.uri, candidate.md5, candidate.size,
                base, destfile=destfile)
            acq.run()
            if acqfile.status != acqfile.STAT_DONE:
                raise FetchError(
                    "The item %r could not be fetched: %s" %
                    (acqfile.destfile, acqfile.error_text))
            result_package = FetchedPackage(
                candidate.package.name, candidate.version, base,
                open(destfile), candidate.size, candidate.md5)
            results.append(result_package)
        return results
