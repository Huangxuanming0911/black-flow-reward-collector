from __future__ import annotations

import argparse
from pathlib import Path

from .ui import run_app


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="blackflow-reward-collector"
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="output root; defaults to current working directory",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    run_app(args.project_root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

