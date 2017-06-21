#!/usr/bin/env python
from __future__ import absolute_import, division, print_function

from argparse import ArgumentParser, Namespace  # pylint: disable=unused-import
from re import search
from sys import argv
from typing import Any, BinaryIO, Callable, Dict, Iterable, List, Optional, Tuple  # pylint: disable=unused-import
from urllib import urlretrieve
try:
    from urllib2 import urlopen
except ImportError:
    from urllib import urlopen  # type: ignore  # pylint: disable=ungrouped-imports
from ports import Platform, PortError, Ports
from ports.cran import Cran, CranPort
from ports.core.port import PortLicense  # pylint: disable=unused-import


__author__ = "Davd Naylor <dbn@FreeBSD.org>"
__license__ = "BSD (FreeBSD)"
__summary__ = "Generates FreeBSD Ports from CRAN packages"
__version__ = "0.1.5"


class Command(object):
    def __init__(self, description):
        # type: (str) -> None
        self._parser = ArgumentParser(description=description)
        self._subparsers = self._parser.add_subparsers(title="available sub-commands", help="sub-command help")

    def execute(self, args):
        # type: (List[str]) -> None
        parsed_args = self._parser.parse_args(args)
        parsed_args.action(parsed_args)

    def usage(self):
        # type: () -> None
        self._parser.print_usage()

    def __call__(self, verb, description):
        # type: (str, str) -> Callable[[Callable[[Namespace], None]], ArgumentParser]
        def decorator(action):
            # type: (Callable[[Namespace], None]) -> ArgumentParser
            parser = self._subparsers.add_parser(verb, help=description)
            parser.set_defaults(action=action)
            return parser
        return decorator


def make_cran_port(name, portdir=None):
    # type: (str, Optional[str]) -> CranPort
    print("Checking for latest version...")
    site_page = urlopen("http://cran.r-project.org/package=%s" % name).read()
    version = search(r"<td>Version:</td>\s*<td>(.*?)</td>", site_page).group(1)
    distfile = Ports.distdir / ("%s_%s.tar.gz" % (name, version))
    if not distfile.exists():  # pylint: disable=no-member
        print("Fetching package source...")
        urlretrieve("https://cran.r-project.org/src/contrib/%s" % distfile.name, distfile)  # pylint: disable=no-member
    return CranPort.create(name, distfile, portdir)


def diff(left, right):
    # type: (Iterable[str], Iterable[str]) -> Tuple[List[str], bool, List[str]]
    left = list(left)
    right = list(right)
    old = [i for i in left if i not in right]
    new = [i for i in right if i not in left]
    left = [i for i in left if i not in old]
    right = [i for i in right if i not in new]
    return old, left == right, new


def log_depends(log, depend, difference):
    # type: (BinaryIO, str, Tuple[List[str], bool, List[str]]) -> None
    old, common, new = difference
    if not common:
        log.write(" - order %s dependencies lexicographically on origin\n" % depend)
    if old:
        log.write(" - remove unused %s dependencies:\n" % depend)
        for i in sorted(old):
            log.write("   - %s\n" % i)
    if new:
        log.write(" - add new %s dependencies:\n" % depend)
        for i in sorted(new):
            log.write("   - %s\n" % i)


def log_uses(log, difference):
    # type: (BinaryIO, Tuple[List[str], bool, List[str]]) -> None
    old, common, new = difference
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
    # type: (BinaryIO, PortLicense, PortLicense) -> None
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

        if list(sorted(old.license)) != list(sorted(new.license)) or old.license.combination != new.license.combination:
            log.write(" - updated license to align with CRAN package\n")
        if old.license.file is None and new.license.file is not None:
            log.write(" - added license file from CRAN package\n")
        elif old.license.file is not None and new.license.file is None:
            log.write(" - removed license file (no longer in CRAN package)\n")

        for depend in ("build", "lib", "run", "test"):
            old_depends = getattr(old.depends, depend)
            new_depends = getattr(new.depends, depend)
            log_depends(log, depend, diff([i.origin for i in old_depends], sorted(i.origin for i in new_depends)))

        if new.distversion in new.changelog:
            assert new.distversion is not None
            log.write(" - changelog:\n")
            for line in new.changelog[new.distversion]:
                log.write("   -")
                length = 4
                for word in line.split(" "):
                    length += len(word) + 1
                    if length > 75:
                        log.write("\n    ")
                        length = 5 + len(word)
                    log.write(" " + word)
                log.write("\n")
        else:
            log.write(" - no changelog provided\n")

        log.write("\nGenerated by:\tportcran (%s)\n" % __version__)


def main():
    # type: () -> None
    command = Command(__summary__)

    @command("update", "update a CRAN port")
    def update(args):
        # type: (Namespace) -> None
        if args.address is not None:
            Platform.address = args.address

        port = Ports.get_port_by_name(Cran.PKGNAMEPREFIX + args.name)
        assert isinstance(port, CranPort)
        cran = make_cran_port(args.name, args.output)
        cran.generate()
        generate_update_log(port, cran)
    update.add_argument("name", help="name of the CRAN package")
    update.add_argument("-o", "--output", help="output directory")
    update.add_argument("-a", "--address", help="creator/maintainer's e-mail address")

    command.execute(argv[1:])

if __name__ == "__main__":
    main()
