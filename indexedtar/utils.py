"""
Utilities to play
with our IndexedTar
"""
from pathlib import Path
from indexedtar import IndexedTar
from math import ceil


def create_super_fat_tar(onefile: Path, fattar_name: Path = Path("fat.tar"), target_size: int = 25*1024**3):
    """
    Given one file,
    keeps adding it to an IndexedTar until the desired size is
    reached
    """

    it = IndexedTar(fattar_name, mode="x:")
    fsize = onefile.lstat().st_size

    count = ceil(target_size / fsize)
    for i in range(count):
        it.add_one_file(onefile, arcname=f"{i}_{onefile.name}")
    it.close()


if __name__ == "__main__":
    create_super_fat_tar(Path("/home/frank/dev/mf-models-on-s3-scraping/arome-france-hd_v2_2021-08-05_00_BRTMP_isobaric_0h.grib2"))