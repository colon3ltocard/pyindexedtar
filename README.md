![example workflow](https://github.com/colon3ltocard/pyindexedtar/actions/workflows/build.yml/badge.svg)
# pyindexedtar

An indexed Tar for big data archives featuring fast random access with an index bundled inside the tarfile.

The use case is to retrieve members of a "many members" tar archive without seeking
from one member to the next.

* [Goals](https://github.com/colon3ltocard/pyindexedtar#goals)
* [Installation](https://github.com/colon3ltocard/pyindexedtar#installation)
* [Usage of the `itar` cli](https://github.com/colon3ltocard/pyindexedtar#usage-of-the-itar-cli)
* [Usage of the `IndexedTar` class](https://github.com/colon3ltocard/pyindexedtar#usage-of-the-indexedtar-class)
* [Benchmark](https://github.com/colon3ltocard/pyindexedtar#benchmark)
* [Concept](https://github.com/colon3ltocard/pyindexedtar#concept)

# Goals

We constrained this code as follows:

* Produce archives fully compliant with the tar specification to
preserve compatibility with existing tools

* No additional index file, the archive should contain the index and be 'all inclusive'

* Use only the python standard library

# Installation

For now I haven't released on pypi.

```
python setup.py install
```

Note: when using pyenv I needed to reactivate my virtualenv post-install to have the **itar** cli available.

# Launching unit tests

Linting and unit tests require additional dependencies.

```shell
pip install -r requirements.txt
$ flake8 --max-line-length 120 indexedtar
$ black --check indexedtar
$ export PYTHONPATH="."; py.test --cov=indexedtar tests
...                                                                                                                     [ 88%]
tests/test_itar.py .                                                                                                                                                                      [100%]

---------- coverage: platform linux, python 3.8.12-final-0 -----------
Name                     Stmts   Miss  Cover
--------------------------------------------
indexedtar/__init__.py     172      6    97%
indexedtar/itar.py          37      4    89%
--------------------------------------------
TOTAL                      209     10    95%

```


# Usage of the `itar` cli

```bash
itar --help
usage: itar [-h] [--target TARGET] [--fnmatch_filter FNMATCH_FILTER] [--output_dir OUTPUT_DIR] action archive

IndexedTar build/extract utility.

positional arguments:
  action                action to perform: "x" for extract, "l" for listing, "c" for create, "a" for append
  archive               path to archive file

optional arguments:
  -h, --help            show this help message and exit
  --target TARGET       file or directory to add
  --fnmatch_filter FNMATCH_FILTER
                        fnmatch filter for listing/extracting archive members
  --output_dir OUTPUT_DIR
                        output directory for extraction
```

Create an archive  with the files in the **tests/data** directory.

```bash
itar c test.tar --target tests/data
```

List archive members matching a fnmatch pattern.

```bash
itar l test.tar --fnmatch_filter "*3h.grib2"
```

Extract members matching a fnmatch pattern to output directory.

```bash
itar x test.tar --fnmatch_filter "*arome*.grib2" --output_dir out
```

# Usage of the `IndexedTar` class

See the [unit tests](https://github.com/colon3ltocard/pyindexedtar/blob/master/tests/test_indexedtar.py) for usage examples.

## Create an archive.

```python
from indexedtar import IndexedTar
DATA_DIR = pathlib.Path("/home/frank/dev/mf-models-on-s3-scraping")
with IndexedTar("test.tar", mode="x:") as it:
    it.add_dir(DATA_DIR)
```
## Get a tarmember by index

```python
with IndexedTar(pathlib.Path("fat.tar"), mode="r:") as it:
    tinfo = it.getmember_at_index(5) # get 5th member from the archive
    print(tinfo.name)
```

## Get and extract members matching a regex or a fnmatch pattern

```python
    with IndexedTar("indexed.tar", "r:") as it:

        # find and extract members using fnmatch
        it.extract_members(it.get_members_fnmatching("2021_01_26/*"))

        # find and extract members using regex
        it.extract_members(it.get_members_re("^2021_02_01"))

        # extract to specific outputdir 'out'
        it.extract_members(it.get_members_fnmatching("*.grib2"), path=Path("out"))
```

# Benchmark

## HDD for a 2.1 GB tarfile with 6094 members

We extract the last member of the archive. See `benchmark.py`.

```
(indexenv) [frank@localhost pyindexedtar]$ python benchmark.py 

python IndexedTar average extraction time: 0.0156 seconds
python Tar average extraction time: 1.5477 seconds
GNU Tar average extraction time: 0.0476 seconds

```
## SSD NVMe with a 2.1 GB tarfile containing 6094 members

Reading 10 random members by name.

```
python IndexedTar average extraction time: 0.0033 seconds
python Tar average extraction time: 0.3216 seconds
GNU Tar average extraction time: 0.0188 seconds
```


## SSD NVMe with a 27 GB tarfile containing 76175 members

Reading 10 random members by name.

```
python IndexedTar average extraction time: 0.0442 seconds
python Tar average extraction time: 3.9926 seconds
GNU Tar average extraction time: 0.1675 seconds
```

# Concept

The trick here is to have a 'normal' binary file
added at the beginning of the tar that serves as a
pre-allocation of 3 unsigned long long to
store header and data offsets + the size of our index.

When we close the archive we write the index
as the last file in the tar and seek back to the
location of the offset and size to write it.

The index itself is a json `_tar_index.json` listing
all the files in the tar including duplicates. For each file we
store its tar header offset, its tar data offset and
its tar data length.

```json
[["my_first_file", 3072, 4608, 352392], ["my_second_file", 357376, 358912, 352392], ["my_third_file", 711680, 713216, 352392]]
```

```
######
_tar_offset.bin tar header
-----
_tar_offset.bin payload
unsigned long long value1 => points to >>>>>------------------|
unsigned long long value2 => points to index data
unsigned long long  value3 => index len                       |
######                                                        |
FILE 1 - tar header                                           |
-----                                                         |
FILE 1 - data          <<<<<<oooooooooooooooooooooooo         |
                                                    o         |
....                                                o         |
                                                    o         |
######                                              o         |
FILE N tar header                                   o         |
-----                                               o         |
FILE N data                                         o         |
######                                              o         |
_tar_index.json - tar header <<<<<<<<<--------------o---------|
------                                              o
_tar_index.json data                                o
[[FILE_1_NAME, FILE_1_TINFO_OFFSET, FILE_1_DATA_OFFSET>, FILE_1_SIZE],
...
[FILE_N_NAME, FILE_N_TINFO_OFFSET, FILE_N_DATA_OFFSET, FILE_N_SIZE]]
######
```

This gives us the following workflow to retrieve a member 'A':
```
open Indexedtar >>> read first member ( = index offset) >>> seek at index offset >>> read index >>> lookup 'A''s offset in index >>> read 'A'.
```

# Compatiblity checks

Our archive stills open with the standard GNU tar cli tool or GUI 7zip client.

![Archive in Ubuntu file explorer](docs/imgs/archive_in_file_explorer.png)

```
(indextarenv)$ tar -tvf fat.tar | most
-rw-r--r-- 0/0              24 2021-09-29 23:50 _tar_offset.bin
-rw-r--r-- frank/frank  352392 2021-09-29 23:48 0_arpege-world_20210827_18_DLWRF_surface_acc_0-3h.grib2
-rw-r--r-- frank/frank  352392 2021-09-29 23:48 1_arpege-world_20210827_18_DLWRF_surface_acc_0-3h.grib2
-rw-r--r-- frank/frank  352392 2021-09-29 23:48 2_arpege-world_20210827_18_DLWRF_surface_acc_0-3h.grib2
-rw-r--r-- frank/frank  352392 2021-09-29 23:48 3_arpege-world_20210827_18_DLWRF_surface_acc_0-3h.grib2
-rw-r--r-- frank/frank  352392 2021-09-29 23:48 4_arpege-world_20210827_18_DLWRF_surface_acc_0-3h.grib2
-rw-r--r-- frank/frank  352392 2021-09-29 23:48 5_arpege-world_20210827_18_DLWRF_surface_acc_0-3h.grib2
...
```

# Todo and ideas

* add highwayhash (SIMD, should perform ! ) checksums for each file in the index
* See if we could handle 'tar.gz' compressed archive using ["IndexedGzip"]("https://github.com/pauldmccarthy/indexed_gzip") ?