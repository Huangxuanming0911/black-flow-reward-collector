from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
import shutil

from blackflow_rewards.store import RewardStore


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply an audited component correction to one reward sample."
    )
    parser.add_argument("sample_id")
    parser.add_argument("--normal", required=True, type=int)
    parser.add_argument("--unowned", required=True, type=int)
    parser.add_argument(
        "--records",
        type=Path,
        default=Path("data/records"),
    )
    parser.add_argument("--note", default="")
    args = parser.parse_args()
    if args.normal < 0 or args.unowned < 0:
        parser.error("component values cannot be negative")

    store = RewardStore(args.records)
    records = store.read_all()
    matched = 0
    for record in records:
        if record.get("sample_id") != args.sample_id:
            continue
        matched += 1
        record["normal_reward_ingots"] = args.normal
        record["unowned_wealth_ingots"] = args.unowned
        record["originium_ingots"] = args.normal + args.unowned
        record["schema_version"] = "0.2.0"
        if args.note:
            previous = str(record.get("reviewer_notes", "")).strip()
            record["reviewer_notes"] = (
                f"{previous}；{args.note}" if previous else args.note
            )
    if matched != 1:
        raise SystemExit(
            f"expected exactly one sample {args.sample_id!r}, found {matched}"
        )

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = store.jsonl_path.with_suffix(f".jsonl.{timestamp}.bak")
    shutil.copy2(store.jsonl_path, backup)
    store.jsonl_path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    store.rebuild_outputs()
    print(f"updated {args.sample_id}; backup: {backup}")


if __name__ == "__main__":
    main()
