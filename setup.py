from setuptools import find_packages, setup


def get_requirements(env=""):
    if env:
        env = "-{}".format(env)
    with open("requirements{}.txt".format(env)) as fp:
        return [x.strip() for x in fp.read().split("\n") if not x.startswith("#")]


setup(
    name="permit",
    version="2.1.0",
    packages=find_packages(),
    author="Asaf Cohen",
    author_email="asaf@permit.io",
    license="Apache 2.0",
    python_requires=">=3.8",
    description="Permit.io python sdk",
    install_requires=get_requirements(),
    classifiers=[
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
)
