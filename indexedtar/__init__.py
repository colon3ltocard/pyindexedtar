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
pre-allocation of 2 unsigned long long to
store offset and size of our index.

When we close the archive we write the index
as the last file in the tar and seek back to the
location of the offset and size to write it.

######
_tar_offset.bin tar header
-----
_tar_offset.bin payload
unsigned long long value1 => points to >>>>>------------------|
unsigned long long  value2 => index len                       | 
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
import io
import json
import pathlib
import tempfile
from contextlib import contextmanager
from typing import IO
import logging


logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())
logger.setLevel("DEBUG")


class IndexTarException(Exception):
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
    _header_struct = struct.Struct(">QQ")
    _index_pax_key = "index_seek_offset"
    _header_offset_in_tar = None

    def __init__(self, filepath: pathlib.Path, mode: str = "r:") -> None:
        """
        We open the archive in read-only or write-only
        """

        if mode not in self._allowed_tar_modes:
            raise IndexTarException(f"Requested {mode=} is not supported (must be in {self._allowed_tar_modes})")

        self._tarfile = tarfile.open(filepath, mode=mode, format=tarfile.PAX_FORMAT)
        
        if mode in ("r:", "a:"):
            logger.debug(f"Opening {filepath.name}, pax-headers: {self._tarfile.pax_headers}")

            header_offset = self._tarfile.next().offset_data
            logger.debug(f"Seeking header offset at {header_offset}")
            with seek_at_and_restore(self._tarfile.fileobj, header_offset):
                index_offset, index_size = self._header_struct.unpack(self._tarfile.fileobj.read(self._header_struct.size))
            
            logger.debug(f"Seeking index json at {index_offset} of len {index_size}")
            with seek_at_and_restore(self._tarfile.fileobj, index_offset):
                raw_index = self._tarfile.fileobj.read(index_size).decode("utf-8")
                self._index = json.loads(raw_index)

        else:
            self._init_header()
            self._index = list()

    def _init_header(self):
        """
        We add at the beginning of the archive a binary file to store our offset to the index
        file
        """
        if len(self._tarfile.getmembers()) > 0:
            raise IndexTarException("_init_header MUST be called at archive creation")

        tinfo = tarfile.TarInfo(self._header_filename)
        tinfo.size = self._header_struct.size
        tinfo.mtime = time.time()
        self._header_offset_in_tar = self._tarfile.offset + self._get_tarinfo_size(tinfo)
        self._tarfile.addfile(tinfo, fileobj=io.BytesIO(initial_bytes=b"0x00"*tinfo.size))
        logger.debug(f"Header offset in tar is {self._header_offset_in_tar}")

    def _get_tarinfo_size(self, tinfo: tarfile.TarInfo):
        """
        Given a TarInfo, returns its size
        in our TarFile context
        """
        return len(tinfo.tobuf(self._tarfile.format, self._tarfile.encoding, self._tarfile.errors))

    def add_one_file(self, filepath: pathlib.Path, arcname=None):
        """
        Adds one file to the tar archive and indexes its seek offset
        """
        if not filepath.is_file():
            raise IndexTarException(f"only files can be added to an IndexedTar, {filepath} is not a file.")

        logger.debug(f"Adding {filepath} to {self._tarfile.name}")
        tinfo_offset = self._tarfile.offset
        tinfo = self._tarfile.gettarinfo(filepath, arcname=arcname)
        data_offset = tinfo_offset + self._get_tarinfo_size(tinfo)
        with open(filepath, "rb") as src:
            self._tarfile.addfile(tinfo, fileobj=src)
        self._index.append((tinfo.name, tinfo_offset, data_offset, tinfo.size))

    def add_dir(self, dir2archive: pathlib.Path, recurse=False):
        """
        Adds a directory content, optionaly descending
        into subdirs
        """
        if not dir2archive.is_dir():
            raise IndexTarException(f"{dir2archive} MUST be a dir")
        
        if recurse:
            for f in dir2archive.rglob("*"):
                if f.is_file():
                    self.add_one_file(f)
        else:
            for f in dir2archive.iterdir():
                if f.is_file():
                    self.add_one_file(f)

    def getmember_at_index(self, index: int) -> tarfile.TarInfo:
        """
        Returns themember at index from the archive 
        """
        _, info_offset, _, _ = self._index[index]
        self._tarfile.offset = info_offset
        return self._tarfile.next()

    def get_members_by_name(self, name: str):
        """
        Generator of members matching a name
        """
        for mname, m_info_offset, _ , _ in self._index:
            if mname == name:
                self._tarfile.offset = m_info_offset
                yield self._tarfile.next()

    def close(self):
        """
        Writes the index, seeks back to our header to write
        the index offset and finally closes the tar archive
        """

        if self._header_offset_in_tar is None:
            raise IndexTarException("Cannot close this archive")

        logger.debug(f"Closing IndexedTar {self._tarfile.name}")
        with tempfile.NamedTemporaryFile("r+b") as tmp:
            index_json = json.dumps(self._index).encode("utf-8")
            tmp.write(index_json)
            tmp.flush()
            tmp.seek(0)
            tinfo = self._tarfile.gettarinfo(tmp.name, arcname=self._index_filename)
            data_offset = self._tarfile.offset + self._get_tarinfo_size(tinfo)
            self._tarfile.addfile(tinfo, fileobj=tmp)

            # now we need to seek at the beginning of the archive and write our
            # header file pointing to this index

            logger.debug(f"Overwriting header at {self._header_offset_in_tar} with {(data_offset, tinfo.size)}")
            with seek_at_and_restore(self._tarfile.fileobj, self._header_offset_in_tar):
                self._tarfile.fileobj.write(self._header_struct.pack(data_offset, tinfo.size))
            self._tarfile.fileobj.flush()

            self._tarfile.close()
            self._tarfile = None

