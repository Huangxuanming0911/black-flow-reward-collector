from __future__ import annotations

import argparse
from pathlib import Path

from blackflow_rewards.store import RewardStore


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Correct one confirmed reward record with an audit note."
    )
    parser.add_argument("sample_id")
    parser.add_argument("--combat-context", required=True)
    parser.add_argument("--note", default="")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
    )
    args = parser.parse_args()
    store = RewardStore(
        args.project_root.resolve() / "data" / "records"
    )
    backup = store.correct_combat_context(
        args.sample_id,
        args.combat_context,
        args.note,
    )
    print(f"corrected={args.sample_id}")
    print(f"combat_context={args.combat_context}")
    print(f"backup={backup}")


if __name__ == "__main__":
    main()
