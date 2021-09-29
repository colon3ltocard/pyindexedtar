"""
Command line program to
work with IndexedTar
"""
from pathlib import Path
import argparse
from indexedtar import IndexedTar, logger


class IndexedTarCliException(Exception):
    pass


parser = argparse.ArgumentParser(description="IndexedTar build/extract utility.")
parser.add_argument(
    "action",
    type=str,
    help='action to perform: "x" for extract, "l" for listing, "c" for create, "a" for append',
)
parser.add_argument("archive", type=Path, help="path to archive file")
parser.add_argument(
    "--target", type=Path, help="file or directory to add", action="append"
)
parser.add_argument(
    "--fnmatch_filter",
    type=str,
    help="fnmatch filter for listing/extracting archive members",
    default="*",
)
parser.add_argument(
    "--output_dir", type=str, help="output directory for extraction", default=Path(".")
)


ALLOWED_ACTIONS = ("x", "l", "c", "a")


def main(test_override: list = None):
    args = (
        parser.parse_args()
        if test_override is None
        else parser.parse_args(test_override)
    )
    action = args.action
    if args.action not in ALLOWED_ACTIONS:
        raise IndexedTarCliException(
            f"Unknown action '{action}', must be in {ALLOWED_ACTIONS}"
        )

    logger.info(f"Processing archive: {args.archive}")

    if action == "l":
        with IndexedTar(args.archive) as it:
            for m in it.get_members_fnmatching(args.fnmatch_filter):
                print(f"{m.name}")

    elif action in ("c", "a"):
        mode = {"c": "x:", "a": "a:"}[action]
        with IndexedTar(args.archive, mode=mode) as it:
            for f in args.target:
                logger.info(f"Adding {str(f)} to {args.archive}")
                if f.is_file():
                    it.add(f)
                elif f.is_dir():
                    it.add_dir(f, recurse=True)

    elif action == "x":
        with IndexedTar(args.archive) as it:
            logger.info(
                f"Extracting with filter {args.fnmatch_filter} to {args.output_dir}"
            )
            it.extract_members(
                it.get_members_fnmatching(args.fnmatch_filter), path=args.output_dir
            )


if __name__ == "__main__":
    main()
