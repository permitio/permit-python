from pathlib import Path

from setuptools import find_packages, setup


def get_requirements() -> list:
    """Read the runtime requirements, ignoring comments and blank lines.

    The blank-line filter matters: requirements.txt ends with a newline, so a
    naive split produced a trailing empty-string "requirement".
    """
    with Path("requirements.txt").open() as fp:
        return [line.strip() for line in fp if line.strip() and not line.startswith("#")]


def get_readme() -> str:
    this_directory = Path(__file__).parent
    return (this_directory / "README.md").read_text()


setup(
    name="permit",
    version="3.0.0",
    # `tests` must be excluded explicitly. A bare find_packages() picks it up and
    # installs it as a TOP-LEVEL `tests` package in the consumer's
    # site-packages, where it shadows their own `tests` module -- verified
    # against the published permit==2.8.3, which does exactly that. `harness` is
    # excluded for the same reason: it is a local developer tool.
    packages=find_packages(exclude=["tests", "tests.*", "harness", "harness.*"]),
    # py.typed tells type checkers to read permit's annotations (PEP 561), and
    # _sync_types.pyi is how they see the blocking client. Neither is a .py
    # file. setuptools 69 and later put both in the wheel by default, but older
    # releases leave them out, and with no [build-system] table in
    # pyproject.toml a build may run with one. Listing them here keeps them in
    # the wheel whichever setuptools builds it.
    package_data={"permit": ["py.typed", "_sync_types.pyi"]},
    author="Asaf Cohen",
    author_email="asaf@permit.io",
    license="Apache 2.0",
    python_requires=">=3.10",
    description="Permit.io python sdk",
    install_requires=get_requirements(),
    long_description=get_readme(),
    long_description_content_type="text/markdown",
    classifiers=[
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "Typing :: Typed",
    ],
)
