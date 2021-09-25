"""
Simple cli to compare
IndexTar versus Tarfile
"""

import tarfile
import pathlib
import sys
import argparse
from indexedtar import IndexedTar


def test_read(src: pathlib.Path):
    it = IndexedTar(src, mode="r:")
    print([x for x in it.get_members_by_name("8125_arome-france-hd_v2_2021-08-05_00_BRTMP_isobaric_0h.grib2")])


def test_read_builtin_tar(src: pathlib.Path):
    it = tarfile.TarFile(src, mode="r")
    tinfo = it.getmember("8125_arome-france-hd_v2_2021-08-05_00_BRTMP_isobaric_0h.grib2")
    print(tinfo)

parser = argparse.ArgumentParser()
parser.add_argument("tarfile", type=pathlib.Path)
parser.add_argument("--mode", default="indexed")

if __name__ == "__main__":
    args = parser.parse_args()
    if args.mode =="indexed":
        test_read(args.tarfile)
    else:
        test_read_builtin_tar(args.tarfile)