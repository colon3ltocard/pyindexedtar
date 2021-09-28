from setuptools import setup

setup(
    author="Frank Guibert",
    author_email="frank.guibert.work@gmail.com",
    name='indexedtar',
    url = "https://github.com/colon3ltocard/pyindexedtar",
    version="1.0",
    license="MIT",
    python_requires='>=3.8',
    description="python class to build uncompressed indexed tar archives for fast read",
    keywords = ['tar', 'indexed', 'archives'],
    packages=("indexedtar",),
)