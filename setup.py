#! /usr/bin/env python3

from __future__ import print_function
import io
import sys
import os
from os.path import isfile, join as pjoin
from glob import glob
from setuptools import setup, find_packages, Command, Extension
from setuptools.command.build_ext import build_ext as _build_ext
from setuptools.errors import SetupError
from distutils import log
from distutils.util import convert_path
import subprocess as sp
import contextlib
import re
import sysconfig

# Force distutils to use py_compile.compile() function with 'doraise' argument
# set to True, in order to raise an exception on compilation errors
import py_compile

orig_py_compile = py_compile.compile


def doraise_py_compile(file, cfile=None, dfile=None, doraise=False):
    orig_py_compile(file, cfile=cfile, dfile=dfile, doraise=True)


py_compile.compile = doraise_py_compile

setup_requires = []

if {"bdist_wheel"}.intersection(sys.argv):
    setup_requires.append("wheel")

if {"release"}.intersection(sys.argv):
    setup_requires.extend(["bump2version", "readme_renderer"])

try:
    __import__("cython")
except ImportError:
    has_cython = False
else:
    has_cython = True

env_with_cython = os.environ.get("FONTTOOLS_WITH_CYTHON")
with_cython = (
    True
    if env_with_cython in {"1", "true", "yes"}
    else False if env_with_cython in {"0", "false", "no"} else None
)
# --with-cython/--without-cython options override environment variables
opt_with_cython = {"--with-cython"}.intersection(sys.argv)
opt_without_cython = {"--without-cython"}.intersection(sys.argv)
if opt_with_cython and opt_without_cython:
    sys.exit(
        "error: the options '--with-cython' and '--without-cython' are "
        "mutually exclusive"
    )
elif opt_with_cython:
    sys.argv.remove("--with-cython")
    with_cython = True
elif opt_without_cython:
    sys.argv.remove("--without-cython")
    with_cython = False

if with_cython and not has_cython:
    setup_requires.append("cython")

ext_modules = []
if with_cython is True or (with_cython is None and has_cython):
    # On POSIX systems (Linux, macOS, etc.), math functions like sqrt, pow, fabs
    # may require explicit linkage to libm. This is particularly needed on some
    # Linux distributions (e.g., Amazon Linux with Clang) where libm is not
    # automatically linked. On Windows, math functions are in msvcrt.
    # See https://github.com/fonttools/fonttools/issues/4028
    libraries = ["m"] if os.name == "posix" else []

    ext_modules.append(
        Extension(
            "fontTools.cu2qu.cu2qu",
            ["Lib/fontTools/cu2qu/cu2qu.py"],
            libraries=libraries,
        ),
    )
    ext_modules.append(
        Extension(
            "fontTools.qu2cu.qu2cu",
            ["Lib/fontTools/qu2cu/qu2cu.py"],
            libraries=libraries,
        ),
    )
    ext_modules.append(
        Extension(
            "fontTools.misc.bezierTools",
            ["Lib/fontTools/misc/bezierTools.py"],
            libraries=libraries,
        ),
    )
    ext_modules.append(
        Extension(
            "fontTools.pens.momentsPen",
            ["Lib/fontTools/pens/momentsPen.py"],
            libraries=libraries,
        ),
    )
    ext_modules.append(
        Extension("fontTools.varLib.iup", ["Lib/fontTools/varLib/iup.py"]),
    )
    ext_modules.append(
        Extension("fontTools.feaLib.lexer", ["Lib/fontTools/feaLib/lexer.py"]),
    )

extras_require = {
    # for fontTools.varLib.avar.reverse, to invert axis variation mappings
    # (no PyPy wheels for scipy; reverse mapping is simply unavailable there)
    "avar": ["scipy; platform_python_implementation != 'PyPy'"],
    # for fontTools.ufoLib: to read/write UFO fonts (kept for backwards compatibility).
    # NOTE: pyfilesystem2 is no longer maintained though it may still continue to work
    # with fontTools.ufoLib for a while; however we no longer depend on it, and instead
    # maintain our own drop-in replacement in fontTools.misc.filesystem.
    "ufo": [
        # "fs >= 2.2.0, < 3",
    ],
    # for fontTools.misc.etree and fontTools.misc.plistlib: use lxml to
    # read/write XML files (faster/safer than built-in ElementTree)
    "lxml": [
        "lxml >= 4.0",
    ],
    # for fontTools.sfnt and fontTools.woff2: to compress/uncompress
    # WOFF 1.0 and WOFF 2.0 webfonts.
    "woff": [
        "brotli >= 1.2.1; platform_python_implementation == 'CPython'",
        "brotlicffi >= 1.2.1.0; platform_python_implementation != 'CPython'",
        "zopfli >= 0.1.4",
    ],
    # for fontTools.unicode and fontTools.unicodedata: to use the latest version
    # of the Unicode Character Database instead of the built-in unicodedata
    # which varies between python versions and may be outdated.
    "unicode": [
        "unicodedata2 >= 18.0.0; python_version <= '3.15'",
    ],
    # for graphite type tables in ttLib/tables (Silf, Glat, Gloc)
    "graphite": ["lz4 >= 1.7.4.2"],
    # for fontTools.interpolatable: to solve the "minimum weight perfect
    # matching problem in bipartite graphs" (aka Assignment problem)
    "interpolatable": [
        # use pure-python alternative on pypy
        "scipy; platform_python_implementation != 'PyPy'",
        "munkres; platform_python_implementation == 'PyPy'",
        # to output PDF or HTML reports. NOTE: wheels are only available for
        # windows currently, other platforms will need to build from source.
        "pycairo",
    ],
    # for fontTools.varLib.plot, to visualize DesignSpaceDocument and resulting
    # VariationModel
    "plot": [
        # TODO: figure out the minimum version of matplotlib that we need
        "matplotlib",
    ],
    # for fontTools.misc.symfont, module for symbolic font statistics analysis
    "symfont": [
        "sympy",
    ],
    # To get file creator and type of Macintosh PostScript Type 1 fonts (macOS only)
    "type1": [
        "xattr; sys_platform == 'darwin'",
    ],
    # for fontTools.ttLib.removeOverlaps, to remove overlaps in TTF fonts
    "pathops": [
        "skia-pathops >= 0.5.0",
    ],
    # for packing GSUB/GPOS tables with Harfbuzz repacker
    "repacker": [
        "uharfbuzz >= 0.45.0",
    ],
}
# use a special 'all' key as shorthand to includes all the extra dependencies
extras_require["all"] = sum(extras_require.values(), [])


# Trove classifiers for PyPI
classifiers = {
    "classifiers": [
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Environment :: Other Environment",
        "Intended Audience :: Developers",
        "Intended Audience :: End Users/Desktop",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "Programming Language :: Python :: 3.15",
        "Programming Language :: Python :: 3",
        "Topic :: Text Processing :: Fonts",
        "Topic :: Multimedia :: Graphics",
        "Topic :: Multimedia :: Graphics :: Graphics Conversion",
    ]
}


# concatenate README.rst and NEWS.rest into long_description so they are
# displayed on the FontTols project page on PyPI
with io.open("README.rst", "r", encoding="utf-8") as readme:
    long_description = readme.read()
long_description += "\nChangelog\n~~~~~~~~~\n\n"
# At the same time, we don't want the PyPI package description becoming too
# long (some tools like Azure DevOps impose maximum length of 324KB) so we
# trim it when we see a special rst comment
changelog_limit_re = re.compile(r"^\.\. package description limit")
with io.open("NEWS.rst", "r", encoding="utf-8") as changelog:
    short_changelog = []
    for line in changelog:
        if changelog_limit_re.match(line):
            break
        short_changelog.append(line)
short_changelog.append(
    "\\... see `here <https://github.com/fonttools/fonttools/blob/main/NEWS.rst>`__ "
    "for earlier changes\n"
)
long_description += "".join(short_changelog)


@contextlib.contextmanager
def capture_logger(name):
    """Context manager to capture a logger output with a StringIO stream."""
    import logging

    logger = logging.getLogger(name)
    try:
        import StringIO

        stream = StringIO.StringIO()
    except ImportError:
        stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger.addHandler(handler)
    try:
        yield stream
    finally:
        logger.removeHandler(handler)


class release(Command):
    """
    Tag a new release with a single command, using the 'bumpversion' tool
    to update all the version strings in the source code.
    The version scheme conforms to 'SemVer' and PEP 440 specifications.

    Firstly, the pre-release '.devN' suffix is dropped to signal that this is
    a stable release. If '--major' or '--minor' options are passed, the
    the first or second 'semver' digit is also incremented. Major is usually
    for backward-incompatible API changes, while minor is used when adding
    new backward-compatible functionalities. No options imply 'patch' or bug-fix
    release.

    A new header is also added to the changelog file ("NEWS.rst"), containing
    the new version string and the current 'YYYY-MM-DD' date.

    All changes are committed, and an annotated git tag is generated. With the
    --sign option, the tag is GPG-signed with the user's default key.

    Finally, the 'patch' part of the version string is bumped again, and a
    pre-release suffix '.dev0' is appended to mark the opening of a new
    development cycle.

    Links:
    - http://semver.org/
    - https://www.python.org/dev/peps/pep-0440/
    - https://github.com/c4urself/bump2version
    """

    description = "update version strings for release"

    user_options = [
        ("major", None, "bump the first digit (incompatible API changes)"),
        ("minor", None, "bump the second digit (new backward-compatible features)"),
        ("sign", "s", "make a GPG-signed tag, using the default key"),
        ("allow-dirty", None, "don't abort if working directory is dirty"),
    ]

    changelog_name = "NEWS.rst"
    version_RE = re.compile(r"^[0-9]+\.[0-9]+")
    date_fmt = "%Y-%m-%d"
    header_fmt = "%s (released %s)"
    commit_message = "Release {new_version}"
    tag_name = "{new_version}"
    version_files = [
        "setup.cfg",
        "setup.py",
        "Lib/fontTools/__init__.py",
    ]

    def initialize_options(self):
        self.minor = False
        self.major = False
        self.sign = False
        self.allow_dirty = False

    def finalize_options(self):
        if all([self.major, self.minor]):
            from distutils.errors import DistutilsOptionError

            raise DistutilsOptionError("--major/--minor are mutually exclusive")
        self.part = "major" if self.major else "minor" if self.minor else None

    def check_long_description_syntax(self):
        import readme_renderer.rst

        result = readme_renderer.rst.render(long_description, stream=sys.stderr)
        if result is None:
            raise SetupError(
                "`long_description` has syntax errors in markup"
                " and would not be rendered on PyPI."
            )

    def run(self):
        self.check_long_description_syntax()

        if self.part is not None:
            log.info("bumping '%s' version" % self.part)
            self.bumpversion(self.part, commit=False)
            release_version = self.bumpversion(
                "release", commit=False, allow_dirty=True
            )
        else:
            log.info("stripping pre-release suffix")
            release_version = self.bumpversion("release")
        log.info("  version = %s" % release_version)

        changes = self.format_changelog(release_version)

        self.git_commit(release_version)
        self.git_tag(release_version, changes, self.sign)

        log.info("bumping 'patch' version and pre-release suffix")
        next_dev_version = self.bumpversion("patch", commit=True)
        log.info("  version = %s" % next_dev_version)

    def git_commit(self, version):
        """Stage and commit all relevant version files, and format the commit
        message with specified 'version' string.
        """
        files = self.version_files + [self.changelog_name]

        log.info("committing changes")
        for f in files:
            log.info("  %s" % f)
        if self.dry_run:
            return
        sp.check_call(["git", "add"] + files)
        msg = self.commit_message.format(new_version=version)
        sp.check_call(["git", "commit", "-m", msg], stdout=sp.PIPE)

    def git_tag(self, version, message, sign=False):
        """Create annotated git tag with given 'version' and 'message'.
        Optionally 'sign' the tag with the user's GPG key.
        """
        log.info(
            "creating %s git tag '%s'" % ("signed" if sign else "annotated", version)
        )
        if self.dry_run:
            return
        # create an annotated (or signed) tag from the new version
        tag_opt = "-s" if sign else "-a"
        tag_name = self.tag_name.format(new_version=version)
        proc = sp.Popen(["git", "tag", tag_opt, "-F", "-", tag_name], stdin=sp.PIPE)
        # use the latest changes from the changelog file as the tag message
        tag_message = "%s\n\n%s" % (tag_name, message)
        proc.communicate(tag_message.encode("utf-8"))
        if proc.returncode != 0:
            sys.exit(proc.returncode)

    def bumpversion(self, part, commit=False, message=None, allow_dirty=None):
        """Run bumpversion.main() with the specified arguments, and return the
        new computed version string (cf. 'bumpversion --help' for more info)
        """
        import bumpversion.cli

        args = (
            (["--verbose"] if self.verbose > 1 else [])
            + (["--dry-run"] if self.dry_run else [])
            + (["--allow-dirty"] if (allow_dirty or self.allow_dirty) else [])
            + (["--commit"] if commit else ["--no-commit"])
            + (["--message", message] if message is not None else [])
            + ["--list", part]
        )
        log.debug("$ bumpversion %s" % " ".join(a.replace(" ", "\\ ") for a in args))

        with capture_logger("bumpversion.list") as out:
            bumpversion.cli.main(args)

        last_line = out.getvalue().splitlines()[-1]
        new_version = last_line.replace("new_version=", "")
        return new_version

    def format_changelog(self, version):
        """Write new header at beginning of changelog file with the specified
        'version' and the current date.
        Return the changelog content for the current release.
        """
        from datetime import datetime

        log.info("formatting changelog")

        changes = []
        with io.open(self.changelog_name, "r+", encoding="utf-8") as f:
            for ln in f:
                if self.version_RE.match(ln):
                    break
                else:
                    changes.append(ln)
            if not self.dry_run:
                f.seek(0)
                content = f.read()
                date = datetime.today().strftime(self.date_fmt)
                f.seek(0)
                header = self.header_fmt % (version, date)
                f.write(header + "\n" + "-" * len(header) + "\n\n" + content)

        return "".join(changes)


def find_data_files(manpath="share/man"):
    """Find FontTools's data_files (just man pages at this point).

    By default, we install man pages to "share/man" directory relative to the
    base installation directory for data_files. The latter can be changed with
    the --install-data option of 'setup.py install' sub-command.

    E.g., if the data files installation directory is "/usr", the default man
    page installation directory will be "/usr/share/man".

    You can override this via the $FONTTOOLS_MANPATH environment variable.

    E.g., on some BSD systems man pages are installed to 'man' instead of
    'share/man'; you can export $FONTTOOLS_MANPATH variable just before
    installing:

    $ FONTTOOLS_MANPATH="man" pip install -v .
        [...]
        running install_data
        copying Doc/man/ttx.1 -> /usr/man/man1

    When installing from PyPI, for this variable to have effect you need to
    force pip to install from the source distribution instead of the wheel
    package (otherwise setup.py is not run), by using the --no-binary option:

    $ FONTTOOLS_MANPATH="man" pip install --no-binary=fonttools fonttools

    Note that you can only override the base man path, i.e. without the
    section number (man1, man3, etc.). The latter is always implied to be 1,
    for "general commands".
    """

    # get base installation directory for man pages
    manpagebase = os.environ.get("FONTTOOLS_MANPATH", convert_path(manpath))
    # all our man pages go to section 1
    manpagedir = pjoin(manpagebase, "man1")

    manpages = [f for f in glob(pjoin("Doc", "man", "man1", "*.1")) if isfile(f)]

    data_files = [(manpagedir, manpages)]
    return data_files


class cython_build_ext(_build_ext):
    """Compile *.pyx source files to *.c using cythonize if Cython is
    installed and there is a working C compiler, else fall back to pure python dist.
    """

    def finalize_options(self):
        from Cython.Build import cythonize

        # optionally enable line tracing for test coverage support
        linetrace = os.environ.get("CYTHON_TRACE") == "1"

        directives = {
            "linetrace": linetrace,
            "language_level": 3,
            "embedsignature": True,
        }
        if sys.version_info >= (3, 13):
            directives["freethreading_compatible"] = True

        # Cython does not regenerate an up-to-date .c file when only the compiler
        # directives change, so a .c generated by an earlier non-free-threaded build
        # (e.g. by cibuildwheel) would be reused and lack the GIL-disabled slot.
        free_threaded = bool(sysconfig.get_config_var("Py_GIL_DISABLED"))

        self.distribution.ext_modules[:] = cythonize(
            self.distribution.ext_modules,
            force=linetrace or self.force or free_threaded,
            annotate=os.environ.get("CYTHON_ANNOTATE") == "1",
            quiet=not self.verbose,
            compiler_directives=directives,
        )

        _build_ext.finalize_options(self)

    def build_extensions(self):
        try:
            _build_ext.build_extensions(self)
        except Exception as e:
            if with_cython:
                raise
            from distutils.errors import DistutilsModuleError

            # optional compilation failed: we delete 'ext_modules' and make sure
            # the generated wheel is 'pure'
            del self.distribution.ext_modules[:]
            try:
                bdist_wheel = self.get_finalized_command("bdist_wheel")
            except DistutilsModuleError:
                # 'bdist_wheel' command not available as wheel is not installed
                pass
            else:
                bdist_wheel.root_is_pure = True
            log.error("error: building extensions failed: %s" % e)


cmdclass = {"release": release}

if ext_modules:
    cmdclass["build_ext"] = cython_build_ext


setup_params = dict(
    name="fonttools",
    version="4.68.1.dev0",
    description="Tools to manipulate font files",
    author="Just van Rossum",
    author_email="just@letterror.com",
    maintainer="Behdad Esfahbod",
    maintainer_email="behdad@behdad.org",
    url="http://github.com/fonttools/fonttools",
    license="MIT",
    license_files=["LICENSE", "LICENSE.external"],
    platforms=["Any"],
    python_requires=">=3.11",
    long_description=long_description,
    long_description_content_type="text/x-rst",
    package_dir={"": "Lib"},
    packages=find_packages("Lib"),
    include_package_data=True,
    data_files=find_data_files(),
    ext_modules=ext_modules,
    setup_requires=setup_requires,
    extras_require=extras_require,
    entry_points={
        "console_scripts": [
            "fonttools = fontTools.__main__:main",
            "ttx = fontTools.ttx:main",
            "pyftsubset = fontTools.subset:main",
            "pyftmerge = fontTools.merge:main",
        ]
    },
    cmdclass=cmdclass,
    **classifiers,
)


if __name__ == "__main__":
    setup(**setup_params)
