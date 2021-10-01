"""
Simple cli to compare
IndexTar versus Tarfile
"""
import os
import random
from math import ceil
import tarfile
from pathlib import Path
import time
import tempfile
from indexedtar import IndexedTar


def create_super_fat_tar(
    onefile: Path, fat_tar: Path = Path("fat.tar"), target_size: int = 2 * 1024 ** 3
):
    """
    Given one file,
    keeps adding it to an IndexedTar until the desired size is
    reached
    """
    if fat_tar.exists():
        fat_tar.unlink()

    it = IndexedTar(fat_tar, mode="x:")
    fsize = onefile.lstat().st_size

    count = ceil(target_size / fsize)
    for i in range(count):
        it.add(onefile, arcname=f"{i}_{onefile.name}")
    it.close()


def extract_indexed(src: Path, member_name: str, path: Path = Path(".")):
    with IndexedTar(src, mode="r:") as it:
        mbrs = [x for x in it.get_members_by_name(member_name)]
        it.extract_members(members=mbrs, path=path)


def extract_builtin_tar(src: Path, member_name: str, path: Path = Path(".")):
    with tarfile.TarFile(src, mode="r") as tf:
        tinfo = tf.getmember(member_name)
        tf.extractall(path=path, members=[tinfo])


def extract_gnu_tar(src: Path, member_name: str, path: Path = Path(".")):
    os.system(f'tar -C {str(path)} -xf .benchmark/fat.tar "{str(member_name)}"')


if __name__ == "__main__":
    working_dir = Path(".") / ".benchmark"

    if not working_dir.exists():
        working_dir.mkdir()

    fat_tar = working_dir / "fat.tar"

    if not fat_tar.exists():
        create_super_fat_tar(
            Path("tests/data/arpege-world_20210827_18_DLWRF_surface_acc_0-3h.grib2"),
            fat_tar=fat_tar,
        )
    suffix = "_arpege-world_20210827_18_DLWRF_surface_acc_0-3h.grib2"
    repeat = 10
    random_members = [f"{random.randint(0, 6194)}{suffix}" for _ in range(repeat)]
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        start_time = time.time()
        for rdm in random_members:
            extract_indexed(fat_tar, rdm, path=tdp)
        end_time = time.time()
        assert all((tdp / rdm).exists() for rdm in random_members)
        delta = (end_time - start_time) / repeat
        print(f"python IndexedTar average extraction time: {delta:.4f} seconds")

    with tempfile.TemporaryDirectory() as td:
        start_time = time.time()
        for rdm in random_members:
            extract_builtin_tar(fat_tar, rdm, path=tdp)
        end_time = time.time()
        assert all((tdp / rdm).exists() for rdm in random_members)
        delta = (end_time - start_time) / repeat
        print(f"python Tar average extraction time: {delta:.4f} seconds")

    with tempfile.TemporaryDirectory() as td:
        start_time = time.time()
        for rdm in random_members:
            extract_gnu_tar(fat_tar, rdm, path=tdp)
        end_time = time.time()
        assert all((tdp / rdm).exists() for rdm in random_members)
        delta = (end_time - start_time) / repeat
        print(f"GNU Tar average extraction time: {delta:.4f} seconds")
