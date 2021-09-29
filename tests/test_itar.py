"""
unit tests for our 'itar' cli
"""
import tempfile
from pathlib import Path
import pytest
from indexedtar.itar import main


def test_itar_cli(arpege_grib2: Path, arome_grib2: Path):
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        args = list()
        args.append("c")
        args.append(str(tdp / "test.tar"))
        args.append("--target")
        args.append(str(arpege_grib2))
        args.append("--target")
        args.append(str(arome_grib2))
        main(args)
        assert (tdp / "test.tar").exists()

        # create on an existing archive will raise
        with pytest.raises(OSError):
            main(args)

        # we check that we find our files if we extract in a new tempdir
        with tempfile.TemporaryDirectory() as dst:
            args = list()
            args.append("x")
            args.append(str(tdp / "test.tar"))
            args.append("--output_dir")
            args.append(dst)
            main(args)
            files = [x for x in Path(dst).rglob("*.grib2")]
            assert len(files) == 2
            assert all(
                any(str(x).endswith(y) for y in (arpege_grib2.name, arome_grib2.name))
                for x in files
            )

        # we check our fnmatch_filter
        with tempfile.TemporaryDirectory() as dst:
            args = list()
            args.append("x")
            args.append(str(tdp / "test.tar"))
            args.append("--output_dir")
            args.append(dst)
            args.append("--fnmatch_filter")
            args.append("*arome*")
            main(args)

            assert len(list(Path(dst).rglob("*.grib2"))) == 1

        # we call our list action
        args = list()
        args.append("l")
        args.append(str(tdp / "test.tar"))
        args.append("--fnmatch_filter")
        args.append("*arome*")
        main(args)
