"""
Simple cli to compare
IndexTar versus Tarfile
"""

import tarfile
import pathlib
import sys
import argparse
from indexedtar import IndexedTar


def benchmark_read(src: pathlib.Path, member_name: str):
    it = IndexedTar(src, mode="r:")
    mbrs = [x for x in it.get_members_by_name(member_name)]
    print(mbrs)
    it.extract_members(members=mbrs)


def benchmark_read_builtin_tar(src: pathlib.Path, member_name: str):
    tf = tarfile.TarFile(src, mode="r")
    tinfo = tf.getmember(member_name)
    print(tinfo)
    tf.extractall(path=".", members=[tinfo])


parser = argparse.ArgumentParser()
parser.add_argument("tarfile", type=pathlib.Path)
parser.add_argument("--mode", default="indexed")
parser.add_argument(
    "--member", default="8125_arome-france-hd_v2_2021-08-05_00_BRTMP_isobaric_0h.grib2"
)

if __name__ == "__main__":
    args = parser.parse_args()
    if args.mode == "indexed":
        benchmark_read(args.tarfile, args.member)
    else:
        benchmark_read_builtin_tar(args.tarfile, args.member)
