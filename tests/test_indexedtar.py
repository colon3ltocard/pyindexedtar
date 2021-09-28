import pytest
from indexedtar import IndexedTar, IndexedTarException


def test_read(ithelper):
    """
    Given an indexed tar file, reads it
    """
    with ithelper.build_indexedtarfile(5) as it_path:
        with IndexedTar(it_path, "r:") as it:
            print(it._mode)
            tinfo = next(it.get_members_by_name("_tar_index.json"))
            json.loads(it.extractfile(tinfo).read().decode("utf-8"))
        