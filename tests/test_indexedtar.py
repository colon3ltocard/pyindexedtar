import tarfile
from pathlib import Path
import tempfile
import pytest
from indexedtar import IndexedTar, IndexedTarException


def test_read(ithelper, arome_grib2: Path):
    """
    Given an indexed tar file, reads it
    """
    no_files: int = 5
    with ithelper.build_indexedtarfile(no_files) as it_path:
        with IndexedTar(it_path, "r:") as it:

            with pytest.raises(IndexedTarException):
                tinfo = next(it.get_members_by_name("_tar_index.json"), None)

            for i in range(no_files):
                fname = f"{i}_arome.grib2"
                tinfo = next(it.get_members_by_name(fname))
                assert tinfo.name == fname
                fobj = it.extractfile(tinfo)
                assert len(fobj.read()) == arome_grib2.stat().st_size
                fobj = it.extractfile(tinfo.name)
                assert len(fobj.read()) == arome_grib2.stat().st_size

                tinfo = it.getmember_at_index(i)
                assert tinfo.name == fname

        with tarfile.TarFile(it_path, "r") as tf:
            members = tf.getmembers()
            # we check the underlying tar file has the proper ordering
            assert [x.name for x in members] == [IndexedTar._header_filename] + [
                f"{i}_arome.grib2" for i in range(no_files)
            ] + [IndexedTar._index_filename]


def test_name_matching(ithelper, arome_grib2: Path):
    """
    Test our various tar member matching generators
    """
    no_files = 6
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        with IndexedTar(tdp / "indexed.tar", "x:") as it:
            # let's simulate an archive spawning over
            # several days of data with a jump
            for the_date in ("2021_01_25", "2021_01_26", "2021_02_01"):
                for i in range(no_files):
                    it.add(arome_grib2, arcname=f"{the_date}/{i}_arome_t.grib2")

        with IndexedTar(tdp / "indexed.tar", "r:") as it:
            # Now we read members using our filter methods
            assert len(list(it.get_members_fnmatching("2021_01_26/*"))) == no_files
            assert (
                len(list(it.get_members_fnmatching("2021_01_26/*", do_reversed=True)))
                == no_files
            )
            assert len(list(it.get_members_fnmatching("*"))) == no_files * 3

            assert len(list(it.get_members_re("^2021"))) == no_files * 3
            assert len(list(it.get_members_re("^2021_02_01"))) == no_files
            assert len(list(it.get_members_re("^2021_02_01", True))) == no_files

            assert (
                len(list(it.get_members_by_name("2021_02_01/0_arome_t.grib2", True)))
                == 1
            )
            assert len(list(it.get_members_by_name("2021_02_01/0_arome_t.grib2"))) == 1

            assert it.getmember_at_index(0).name == "2021_01_25/0_arome_t.grib2"


def test_append(ithelper, arome_grib2: Path, arpege_grib2: Path):
    """
    We test appending to an existing IndexedTar.
    A new index should be created and pointed to.
    """
    no_files: int = 8
    with ithelper.build_indexedtarfile(no_files) as it_path:
        with IndexedTar(it_path, "a:") as it:
            it.add(arome_grib2, arcname=f"{no_files}_arome.grib2")
            it.add(arpege_grib2, arcname=f"{no_files+1}_arpege.grib2")

        # Now we read the new files

        with IndexedTar(it_path, "r:") as it:
            for m_name, fp in (
                (f"{no_files}_arome.grib2", arome_grib2),
                (f"{no_files+1}_arpege.grib2", arpege_grib2),
            ):
                tinfo: tarfile.TarInfo = next(it.get_members_by_name(m_name))
                assert tinfo.size == fp.stat().st_size
                fobj = it.extractfile(tinfo)
                assert len(fobj.read()) == fp.stat().st_size

        # and also check the old ones
        with IndexedTar(it_path, "r:") as it:
            for m_name in [f"{i}_arome.grib2" for i in range(no_files)]:
                tinfo: tarfile.TarInfo = next(it.get_members_by_name(m_name))
                assert tinfo.size == arome_grib2.stat().st_size
                fobj = it.extractfile(tinfo)
                assert len(fobj.read()) == arome_grib2.stat().st_size

        # checks the file ordreding in the tar
        # the old and new indices must be here.

        with tarfile.TarFile(it_path, "r") as tf:
            members = tf.getmembers()
            # we check the underlying tar file has the proper ordering
            assert [x.name for x in members] == [IndexedTar._header_filename] + [
                f"{i}_arome.grib2" for i in range(no_files)
            ] + [IndexedTar._index_filename] + [
                f"{no_files}_arome.grib2",
                f"{no_files+1}_arpege.grib2",
            ] + [
                IndexedTar._index_filename
            ]


def test_tar_is_rejected(ithelper):
    """
    A "normal" tar without our specific
    pax_headers and index files must
    raise
    """
    no_files: int = 4
    with ithelper.build_tarfile(no_files) as tf_path:
        with pytest.raises(IndexedTarException):
            IndexedTar(tf_path, "r:")


def test_corruption(ithelper):
    """
    We corrupt the headers, it should raise
    """
    no_files = 2
    with ithelper.build_indexedtarfile(no_files) as it_path:
        for corruption in ((0, 0, 0), (64, 512, 1024 ** 3)):
            ithelper.corrupt_indexed_tar_header(it_path, corruption)
            for mode in ("a:", "r:"):
                with pytest.raises(IndexedTarException):
                    IndexedTar(it_path, mode)


def test_add_dir(data_dir):
    """
    We check the add directory feature works
    """
    with tempfile.TemporaryDirectory() as td:
        itar_path = Path(td) / "indexed.tar"
        with IndexedTar(itar_path, "x:") as it:
            it.add_dir(data_dir)
            it.add_dir(data_dir, recurse=True)  # todo: check with proper nested dirs


def test_extract(ithelper):
    """
    Testing the top level method
    for extracting into a directory
    """
    for numeric_owner in (True, False):
        with tempfile.TemporaryDirectory() as td:
            no_files: int = 4
            with ithelper.build_indexedtarfile(no_files) as itar_path:
                with IndexedTar(itar_path) as it:
                    members = []
                    for i in range(no_files):
                        members.append(next(it.get_members_by_name(f"{i}_arome.grib2")))
                    it.extract_members(members, path=td, numeric_owner=numeric_owner)
                    assert len([x for x in Path(td).glob("*.grib2")]) == 4


def test_edge_cases(ithelper, arpege_grib2: Path):
    """
    we are supposed to raise in several
    edge cases
    """
    no_files: int = 4
    with ithelper.build_indexedtarfile(no_files) as itar_path:
        with IndexedTar(itar_path) as it:
            # adding to a read-only it is forbidden
            with pytest.raises(IndexedTarException):
                it.add(arpege_grib2)

        with IndexedTar(itar_path, "a:") as it:

            # adding a file with add_dir is forbidden
            with pytest.raises(IndexedTarException):
                it.add_dir(arpege_grib2)

            # adding a dir with add is forbidden
            with pytest.raises(IndexedTarException):
                it.add(arpege_grib2.parent)

            # supplying a member of than Union[str, TarInfo] is forbidden
            with pytest.raises(IndexedTarException):
                it.extractfile(arpege_grib2)

            # compression is not supported
            for unsupported_mode in ("r:gz", "r:bz2", "r:xz"):
                with pytest.raises(IndexedTarException):
                    IndexedTar(itar_path, mode=unsupported_mode)

            # A closed IndexedTar object cannot be used as
            # a contextmanager anymore
            it = IndexedTar(itar_path)
            it.close()
            with pytest.raises(IndexedTarException):
                with (it) as itt:
                    itt.get_members_fnmatching("*")
