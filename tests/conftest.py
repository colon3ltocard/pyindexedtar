"""
pytest pre-test code
and shared fixtures
"""

from contextlib import contextmanager
from pathlib import Path
import tarfile
import tempfile
import pytest
from indexedtar import IndexedTar


DATADIR = Path(__file__).parent / "data"
AROME_FILE = DATADIR / "arome-france-hd_v2_2021-08-05_00_BRTMP_isobaric_0h.grib2"


@pytest.fixture(scope="session")
def data_dir():
    return DATADIR


@pytest.fixture(scope="session")
def arome_grib2() -> Path:
    """
    Returns the Path to our arome-hd grib2 testfile
    """
    return AROME_FILE


@pytest.fixture(scope="session")
def arpege_grib2() -> Path:
    """
    Returns the Path to our smaller arpege test file
    """
    return DATADIR / "arpege-world_20210827_18_DLWRF_surface_acc_0-3h.grib2"


class IndexedTarHelper:
    """
    class with utilities
    to perform our tests
    """

    @staticmethod
    def corrupt_indexed_tar_header(itarf: Path, corruption: tuple = (0, 0, 0)):
        """
        given an IndexedTar file, corrupts its header
        """
        print(itarf, itarf.stat().st_size)
        with tarfile.TarFile(itarf, "r") as tf:
            # print(tf.getmembers())
            htinfo = tf.getmember(IndexedTar._header_filename)
        with open(tf.name, "r+b") as dst:
            dst.seek(htinfo.offset_data)
            dst.write(IndexedTar._header_struct.pack(*corruption))

    @staticmethod
    @contextmanager
    def build_tarfile(no_files: int) -> Path:
        """
        Builds a 'classic' tarfile of the desired number of files
        using our 3.3 MB arome data file
        """
        with tempfile.TemporaryDirectory() as dst:
            fp = AROME_FILE
            dst_file = Path(dst) / "basic_tar.tar"
            with tarfile.TarFile(dst_file, mode="x") as tf:
                for i in range(no_files):
                    tf.add(fp, arcname=f"{i}_arome.grib2")

            yield dst_file

    @staticmethod
    @contextmanager
    def build_indexedtarfile(no_files: int) -> Path:
        """
        Builds a 'classic' tarfile of the desired number of files
        using our 3.3 MB arome data file
        """
        with tempfile.TemporaryDirectory() as dst:
            fp = AROME_FILE
            dst_file = Path(dst) / "indexed_tar.tar"
            with IndexedTar(dst_file, mode="x:") as it:
                for i in range(no_files):
                    it.add(fp, arcname=f"{i}_arome.grib2")

            yield dst_file


@pytest.fixture(scope="session")
def ithelper():
    return IndexedTarHelper()
