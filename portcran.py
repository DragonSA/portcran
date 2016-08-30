#!/usr/bin/env python
from __future__ import absolute_import, division, print_function

from argparse import ArgumentParser
from re import match, search
from sys import argv
from tarfile import TarFile
from urllib import urlretrieve
try:
    from urllib2 import urlopen
except ImportError:
    from urllib import urlopen  # type: ignore  # pylint: disable=ungrouped-imports
from plumbum.path import LocalPath
from ports import Platform, PortError, Ports
from ports.cran import Cran, CranPort
from ports.core.internal import Stream
from ports.core.port import PortLicense


__author__ = "Davd Naylor <dbn@FreeBSD.org>"
__license__ = "BSD (FreeBSD)"
__summary__ = "Generates FreeBSD Ports from CRAN packages"
__version__ = "0.1.1"


def match_key(line):
    # type: (str) -> bool
    return bool(match("^[a-zA-Z/@]+:", line))


def make_cran_port(name, portdir=None):
    # type: (str, LocalPath) -> CranPort
    print("Cheching for latest version...")
    site_page = urlopen("http://cran.r-project.org/package=%s" % name).read()
    version = search(r"<td>Version:</td>\s*<td>(.*?)</td>", site_page).group(1)
    distfile = Ports.distdir / ("%s_%s.tar.gz" % (name, version))
    if not distfile.exists():  # pylint: disable=no-member
        print("Fetching package source...")
        urlretrieve("https://cran.r-project.org/src/contrib/%s" % distfile.name, distfile)  # pylint: disable=no-member
    cran = CranPort(["make"], name, portdir)
    try:
        port = Ports.get_port_by_name(Cran.PKGNAMEPREFIX + name)
        cran.category = port.categories[0]
        cran.categories = port.categories
        cran.maintainer = port.maintainer
    except PortError:
        pass
    with TarFile.open(str(distfile), "r:gz") as distfile:
        desc = Stream(i.rstrip('\n') for i in distfile.extractfile("%s/DESCRIPTION" % name).readlines())
    while desc.has_current:
        line = desc.current
        key, value = line.split(":", 1)
        value = value.strip() + "".join(" " + i.strip() for i in desc.take_until(match_key))
        cran.parse(key, value, desc.line)  # type: ignore
    return cran


def diff(left, right):
    # type: (Iterable[str], Iterable[str]) -> (List[str], bool, List[str])
    left = list(left)
    right = list(right)
    old = [i for i in left if i not in right]
    new = [i for i in right if i not in left]
    left = [i for i in left if i not in old]
    right = [i for i in right if i not in new]
    return old, left == right, new


def log_depends(log, depend, diff):
    # type: (file, str, (List[str], bool, List[str])) -> None
    old, common, new = diff
    if not common:
        log.write(" - order %s dependencies lexicographically on origin\n" % depend)
    if len(old):
        log.write(" - remove unused %s dependencies:\n" % depend)
        for i in sorted(old):
            log.write("   - %s\n" % i)
    if len(new):
        log.write(" - add new %s dependencies:\n" % depend)
        for i in sorted(new):
            log.write("   - %s\n" % i)


def log_uses(log, diff):
    # type: (file, (List[str], bool, List[new])) -> None
    old, common, new = diff
    if not common:
        log.write(" - sort cran uses arguments lexicographically\n")
    for arg in old:
        if arg == "auto-plist":
            log.write(" - manually generate pkg-plist\n")
        elif arg == "compiles":
            log.write(" - port no longer needs to compile\n")
        else:
            raise PortError("Log: unknown cran argument: %s" % arg)
    for arg in new:
        if arg == "auto-plist":
            log.write(" - automatically generate pkg-plist\n")
        elif arg == "compiles":
            log.write(" - mark port as needing to compile\n")
        else:
            raise PortError("Log: unknown cran argument: %s" % arg)


def log_license(log, old, new):
    # type: (file, PortLicense, PortLicense) -> None
    if list(old) != list(sorted(new)):
        log.write(" - update license to: %s\n" % " ".join(sorted(new)))
    elif old.combination != new.combination:
        if new.combination is None:
            log.write(" - remove license combination\n")
        else:
            log.write(" - update license combination\n")


def generate_update_log(old, new):
    # type: (CranPort, CranPort) -> None
    assert (old.portversion or old.distversion) != new.distversion
    with open(new.portdir / "commit.svn", "w") as log:
        log.write("%s: updated to version %s\n\n" % (new.origin, new.distversion))
        if old.portrevision is not None:
            log.write(" - removed PORTREVISION due to version bump\n")
        if old.maintainer != new.maintainer:
            log.write(" - update maintainer\n")
        if old.comment != new.comment:
            log.write(" - updated comment to align with CRAN package\n")

        log_depends(log, "run", diff([i.origin for i in old.depends.run], sorted(i.origin for i in new.depends.run)))
        log_depends(log, "test", diff([i.origin for i in old.depends.test], sorted(i.origin for i in new.depends.test)))
        log_uses(log, diff(old.uses(Cran), sorted(new.uses(Cran))))

        log.write("\nGenerated by:\tportcran (%s)\n" % __version__)


def update():
    # type: () -> None
    parser = ArgumentParser()
    parser.add_argument("name", help="Name of the CRAN package")
    parser.add_argument("-o", "--output", help="Output directory")

    parser.add_argument("-a", "--address", help="Creator/maintainer's e-mail address")

    args = parser.parse_args()

    if args.address is not None:
        Platform.address = args.address

    portdir = None if args.output is None else LocalPath(args.output)
    port = Ports.get_port_by_name(Cran.PKGNAMEPREFIX + args.name)
    assert isinstance(port, CranPort)
    cran = make_cran_port(args.name, portdir)
    cran.generate()
    generate_update_log(port, cran)


def main():
    # type: () -> None
    if len(argv) == 1:
        print("usage: portcran update [-o OUTPUT] name")
        exit(2)
    action = argv.pop(1)
    if action == "update":
        update()

if __name__ == "__main__":
    main()
