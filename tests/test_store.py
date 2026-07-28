from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import json
import unittest

from blackflow_rewards.models import RewardRecord
from blackflow_rewards.store import RewardStore


def record(sample_id: str, bonus_source: str) -> RewardRecord:
    return RewardRecord(
        sample_id=sample_id,
        captured_at="2026-07-28T00:00:00+00:00",
        source_floor="3",
        location_context="main_map",
        combat_context="emergency_combat",
        stage_name="预算否决",
        command_xp=33,
        originium_ingots=4,
        normal_reward_ingots=2,
        unowned_wealth_ingots=2,
        hope=0,
        recruitment_tickets=1,
        collectibles=0,
        parts=1,
        bonus_source=bonus_source,
        bonus_details="",
        command_xp_multiplier=1.0,
        ingot_multiplier=1.0,
        displayed_reward_names=("源石锭",),
        settlement_screenshots=("a.jpg",),
        reward_screenshots=("b.jpg",),
        ocr_text="",
        reviewer_notes="",
    )


class RewardStoreTests(unittest.TestCase):
    def test_appends_jsonl_csv_and_excludes_bonus_from_base_summary(self) -> None:
        with TemporaryDirectory() as directory:
            store = RewardStore(Path(directory))
            store.append(record("base", "none"))
            store.append(record("bonus", "chest"))
            self.assertEqual(len(store.read_all()), 2)
            with store.csv_path.open(
                encoding="utf-8-sig",
                newline="",
            ) as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 2)
            summary = json.loads(
                store.summary_path.read_text(encoding="utf-8")
            )
            self.assertEqual(summary["eligible_sample_count"], 1)
            self.assertEqual(summary["groups"][0]["mean_command_xp"], 33.0)
            self.assertEqual(
                summary["groups"][0]["mean_normal_reward_ingots"],
                2.0,
            )
            self.assertEqual(
                summary["groups"][0]["mean_unowned_wealth_ingots"],
                2.0,
            )


if __name__ == "__main__":
    unittest.main()
