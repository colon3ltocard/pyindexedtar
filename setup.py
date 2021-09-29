from setuptools import setup

with open("README.md") as f:
    long_description = f.read()

setup(
    author="Frank Guibert",
    author_email="frank.guibert.work@gmail.com",
    name="indexedtar",
    url="https://github.com/colon3ltocard/pyindexedtar",
    version="1.0",
    license="MIT",
    python_requires=">=3.8",
    description="build/search/extract_from uncompressed indexed tar archives for fast random access. The index is in the tar itself.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    keywords=["tar", "indexed", "archives"],
    packages=("indexedtar",),
    entry_points = {
        'console_scripts': ['itar=indexedtar.itar:main'],
    }
)
