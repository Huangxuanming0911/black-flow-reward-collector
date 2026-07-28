from __future__ import annotations

import argparse
from pathlib import Path

from blackflow_rewards.store import RewardStore


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Correct one confirmed reward record with an audit note."
    )
    parser.add_argument("sample_id")
    parser.add_argument("--combat-context")
    parser.add_argument("--parts", type=int)
    parser.add_argument("--recruitment-tickets", type=int)
    parser.add_argument("--bonus-parts", type=int)
    parser.add_argument("--parts-bonus-details", default="")
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
    if args.combat_context:
        backup = store.correct_combat_context(
            args.sample_id,
            args.combat_context,
            args.note,
        )
    elif args.parts is not None and args.bonus_parts is not None:
        backup = store.correct_parts_breakdown(
            args.sample_id,
            args.parts,
            args.bonus_parts,
            args.parts_bonus_details,
            args.note,
        )
    elif args.recruitment_tickets is not None or args.parts is not None:
        backup = store.correct_reward_counts(
            args.sample_id,
            recruitment_tickets=args.recruitment_tickets,
            parts=args.parts,
            note=args.note,
        )
    else:
        parser.error(
            "provide --combat-context, --recruitment-tickets, --parts, "
            "or both --parts and --bonus-parts"
        )
    print(f"corrected={args.sample_id}")
    if args.combat_context:
        print(f"combat_context={args.combat_context}")
    elif args.parts is not None and args.bonus_parts is not None:
        print(f"parts={args.parts}")
        print(f"bonus_parts={args.bonus_parts}")
    else:
        if args.recruitment_tickets is not None:
            print(
                f"recruitment_tickets={args.recruitment_tickets}"
            )
        if args.parts is not None:
            print(f"parts={args.parts}")
    print(f"backup={backup}")


if __name__ == "__main__":
    main()
