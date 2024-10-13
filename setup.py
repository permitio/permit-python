from pathlib import Path

from setuptools import find_packages, setup


def get_requirements(env=""):
    if env:
        env = f"-{env}"
    with Path(f"requirements{env}.txt").open() as fp:
        return [x.strip() for x in fp.read().split("\n") if not x.startswith("#")]


def get_readme() -> str:
    this_directory = Path(__file__).parent
    long_description = (this_directory / "README.md").read_text()
    return long_description


setup(
    name="permit",
    version="2.6.5",
    packages=find_packages(),
    author="Asaf Cohen",
    author_email="asaf@permit.io",
    license="Apache 2.0",
    python_requires=">=3.8",
    description="Permit.io python sdk",
    install_requires=get_requirements(),
    long_description=get_readme(),
    long_description_content_type="text/markdown",
    classifiers=[
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
)
