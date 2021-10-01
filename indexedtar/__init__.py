"""
A set of tools to work with PAX TarFiles
augmented with an index for fast one shot seek.

The produced archives are still compliant
with the tar specification and can be read
with normal python or cli tools.

Designed to provide speedups with fat tars of 10,25,50 GB
made of many files for a big data archiving software.

The trick here is to have a 'normal' binary file
added at the beginning of the tar that serves as a
pre-allocation of 3 unsigned long long to
store header and data offsets + the size of our index.

When we close the archive we write the index
as the last file in the tar and seek back to the
location of the offset and size to write it.

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
"""
import tarfile
import time
import struct
import fnmatch
import re
import io
import json
from pathlib import Path
import tempfile
from contextlib import contextmanager
from typing import IO, Generator, Union
import logging


logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())
logger.setLevel("INFO")


class IndexedTarException(Exception):
    pass


@contextmanager
def seek_at_and_restore(file: IO, pos: int = 0):
    """
    Seek at and
    restores fp on exit
    """
    try:
        old = file.tell()
        file.seek(pos)
        yield
    finally:
        file.seek(old)


@contextmanager
def set_and_restore(object, attr_name: str, value):
    """
    Stores old object value
    and sets to value.
    On exit restores old value
    """
    try:
        old = getattr(object, attr_name)
        setattr(object, attr_name, value)
        yield
    finally:
        setattr(object, attr_name, old)


class IndexedTar:
    """
    This class provides incremental tar members
    addition but no removal of already written members.
    It builds the seek index on the fly and saves it
    when the archive is closed.
    Compression is disabled.
    """

    _allowed_tar_modes = ("r:", "x:", "a:")
    _index_filename = "_tar_index.json"
    _header_filename = "_tar_offset.bin"
    _header_struct = struct.Struct(">QQQ")
    _index_pax_key = "index_seek_offset"
    _header_offset_in_tar = None
    _version = "1.0.1"

    def __init__(self, filepath: Path, mode: str = "r:") -> None:
        """
        We open the archive in read-only or write-only
        """

        if mode not in self._allowed_tar_modes:
            raise IndexedTarException(
                f"Requested {mode=} is not supported (must be in {self._allowed_tar_modes})"
            )

        self._mode = mode

        if mode in ("r:", "a:"):

            # In append mode we first have to open the tar file in
            # read mode to extract the existing index
            if mode == "a:":
                with tarfile.TarFile(filepath, mode="r") as tf:
                    self._index, self._header_offset_in_tar = self.extract_index(tf)

                self._tarfile = tarfile.open(
                    filepath, mode=mode, format=tarfile.PAX_FORMAT
                )

            else:
                self._tarfile = tarfile.open(
                    filepath, mode=mode, format=tarfile.PAX_FORMAT
                )

                self._index, _ = self.extract_index(self._tarfile)

        else:
            self._tarfile = tarfile.open(
                filepath,
                mode=mode,
                format=tarfile.PAX_FORMAT,
                pax_headers={"indexed_tar": self._version},
            )
            self._init_header()
            self._index = list()

    def extract_index(self, tf: tarfile.TarFile) -> list:
        """
        Extracts the index from TarFile
        """
        filepath = Path(tf.name)
        if "indexed_tar" not in tf.pax_headers:
            raise IndexedTarException(
                f"Attempting to read or append to a non IndexedTar {tf.name}"
            )

        first_member = tf.next()
        if (
            first_member.name != self._header_filename
            or first_member.size != self._header_struct.size
        ):
            raise IndexedTarException(
                f"First file in tar {first_member.name} is not a valid IndexedTar header"
            )
        header_offset = first_member.offset_data
        logger.debug(f"Seeking header offset at {header_offset}")
        with seek_at_and_restore(tf.fileobj, header_offset):
            (
                index_tar_header_offset,
                index_offset,
                index_size,
            ) = self._header_struct.unpack(tf.fileobj.read(self._header_struct.size))

        if index_offset + index_size > filepath.stat().st_size:
            raise IndexedTarException(f"Invalid Index past end of file {filepath.name}")

        logger.debug(f"Reading index tar header at {index_tar_header_offset}")
        with set_and_restore(tf, "offset", index_tar_header_offset):

            try:
                tinfo = tf.next()
            except OSError as ose:
                raise IndexedTarException("Corrupt header") from ose

            if tinfo.name != self._index_filename:
                raise IndexedTarException(
                    f"Invalid index filename, got {tinfo.name}, expected {self._index_filename}"
                )

            if tinfo.size != index_size:
                raise IndexedTarException(
                    "Inconsistency between index size in tar header and indexedtar header, file has been corrupted ?"
                )

        logger.debug(f"Reading index json at {index_offset} of len {index_size}")
        with seek_at_and_restore(tf.fileobj, index_offset):
            raw_index = tf.fileobj.read(index_size).decode("utf-8")

        return json.loads(raw_index), header_offset

    def _init_header(self):
        """
        We add at the beginning of the archive a binary file to store our offset to the index
        file
        """
        if len(self._tarfile.getmembers()) > 0:
            raise IndexedTarException("_init_header MUST be called at archive creation")

        tinfo = tarfile.TarInfo(self._header_filename)
        tinfo.size = self._header_struct.size
        tinfo.mtime = time.time()
        self._header_offset_in_tar = self._tarfile.offset + self._get_tarinfo_size(
            tinfo
        )
        self._tarfile.addfile(
            tinfo, fileobj=io.BytesIO(initial_bytes=b"0x00" * tinfo.size)
        )
        logger.debug(f"Header offset in tar is {self._header_offset_in_tar}")

    def _get_tarinfo_size(self, tinfo: tarfile.TarInfo):
        """
        Given a TarInfo, returns its size
        in our TarFile context
        """
        return len(
            tinfo.tobuf(
                self._tarfile.format, self._tarfile.encoding, self._tarfile.errors
            )
        )

    def add(self, filepath: Path, arcname=None):
        """
        Adds one file to the tar archive and indexes its seek offset
        """
        if not filepath.is_file():
            raise IndexedTarException(
                f"only files can be added to an IndexedTar, {filepath} is not a file."
            )

        if self._mode not in ("x:", "a:"):
            raise IndexedTarException(
                f"Cannot add a file to read only IndexedTar {self._tarfile}"
            )

        logger.debug(f"Adding {filepath} to {self._tarfile.name}")
        tinfo_offset = self._tarfile.offset
        tinfo = self._tarfile.gettarinfo(filepath, arcname=arcname)
        data_offset = tinfo_offset + self._get_tarinfo_size(tinfo)
        with open(filepath, "rb") as src:
            self._tarfile.addfile(tinfo, fileobj=src)
        self._index.append((tinfo.name, tinfo_offset, data_offset, tinfo.size))

    def add_dir(self, dir2archive: Path, recurse=False):
        """
        Adds a directory content, optionaly descending
        into subdirs
        """
        if not dir2archive.is_dir():
            raise IndexedTarException(f"{dir2archive} MUST be a dir")

        if self._mode not in ("x:", "a:"):
            raise IndexedTarException(
                f"Cannot add files to read only IndexedTar {self._tarfile}"
            )

        if recurse:
            for f in dir2archive.rglob("*"):
                if f.is_file():
                    self.add(f)
        else:
            for f in dir2archive.iterdir():
                if f.is_file():
                    self.add(f)

    def getmember_at_index(self, index: int) -> tarfile.TarInfo:
        """
        Returns themember at index from the archive
        """
        _, info_offset, _, _ = self._index[index]
        self._tarfile.offset = info_offset
        return self._tarfile.next()

    def get_members_by_name(
        self, name: str, do_reversed: bool = False
    ) -> Generator[tarfile.TarInfo, None, None]:
        """
        Generator of members matching a name.
        Set do_reversed to true to iterate from the end of the index.
        """

        if name in (self._index_filename, self._header_filename):
            raise IndexedTarException(f"filename {name} is reserved")

        yield from self._get_members_matching(lambda x: x == name, do_reversed)

    def _get_members_matching(
        self, match_func, do_reversed: bool = False
    ) -> Generator[tarfile.TarInfo, None, None]:
        """
        Internal generator over members matching
        a match_func return value
        """
        idx_gen = (
            (x for x in self._index)
            if do_reversed
            else (x for x in reversed(self._index))
        )

        for mname, m_info_offset, _, _ in idx_gen:
            if match_func(mname):
                self._tarfile.offset = m_info_offset
                yield self._tarfile.next()

    def get_members_fnmatching(
        self, pattern: str, do_reversed: bool = False
    ) -> Generator[tarfile.TarInfo, None, None]:
        """
        Generator of members matching a fnmatch pattern.
        Set do_reversed to true to iterate from the end of the index.
        See https://docs.python.org/3/library/fnmatch.html
        """
        regex = fnmatch.translate(pattern)
        yield from self.get_members_re(regex, do_reversed=do_reversed)

    def get_members_re(
        self, regex: str, do_reversed: bool = False
    ) -> Generator[tarfile.TarInfo, None, None]:
        """
        Generator of members matching a regex.
        Set do_reversed to true to iterate from the end of the index.
        See https://docs.python.org/3/library/re.html
        """
        reobj = re.compile(regex)
        yield from self._get_members_matching(
            lambda x: reobj.match(x) is not None, do_reversed
        )

    def extract_members(
        self, members: list, path: Path = Path("."), numeric_owner=False
    ):
        """
        Extracts members into dstdir.
        Same risks and limitations as in python TarFile.
        """
        self._tarfile.extractall(
            path=path, members=members, numeric_owner=numeric_owner
        )

    def close(self):
        """
        Writes the index, seeks back to our header to write
        the index offset and finally closes the tar archive
        """

        if self._mode in ("x:", "a:"):

            if self._header_offset_in_tar is None:
                raise IndexedTarException("Cannot close this archive")

            logger.debug(f"Closing IndexedTar {self._tarfile.name}")
            with tempfile.NamedTemporaryFile("r+b") as tmp:
                index_json = json.dumps(self._index).encode("utf-8")
                tmp.write(index_json)
                tmp.flush()
                tmp.seek(0)
                tinfo = self._tarfile.gettarinfo(tmp.name, arcname=self._index_filename)
                tar_header_offset = self._tarfile.offset
                data_offset = self._tarfile.offset + self._get_tarinfo_size(tinfo)
                self._tarfile.addfile(tinfo, fileobj=tmp)

                # now we need to seek at the beginning of the archive and write our
                # header file pointing to this index

                logger.debug(
                    f"Overwriting header at {self._header_offset_in_tar} with {(data_offset, tinfo.size)}"
                )
                with seek_at_and_restore(
                    self._tarfile.fileobj, self._header_offset_in_tar
                ):
                    self._tarfile.fileobj.write(
                        self._header_struct.pack(
                            tar_header_offset, data_offset, tinfo.size
                        )
                    )
                self._tarfile.fileobj.flush()

        if self._tarfile:
            self._tarfile.close()
        self._tarfile = None

    def __enter__(self):
        if self._tarfile and not self._tarfile.closed:
            return self
        else:
            raise IndexedTarException("IndexedTar is closed")

    def extractfile(self, member: Union[str, tarfile.TarInfo]):
        """Extract a member from the archive as a file object. `member' may be
        a filename or a TarInfo object. If `member' is a regular file or a
        link, an io.BufferedReader object is returned. Otherwise, None is
        returned.
        """
        if isinstance(member, str):
            tinfo = [x for x in self.get_members_by_name(member)][-1]
        elif isinstance(member, tarfile.TarInfo):
            tinfo = member
        else:
            raise IndexedTarException(
                f"Cannot extract {member}, must be an instance of str or TarInfo"
            )

        return self._tarfile.extractfile(tinfo)

    def __exit__(self, type, value, traceback):
        self.close()
        return False
