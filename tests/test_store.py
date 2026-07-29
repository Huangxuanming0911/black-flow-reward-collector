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
        detected_combat_context="emergency_combat",
        context_evidence=("combat_text:紧急作战",),
    )


class RewardStoreTests(unittest.TestCase):
    def test_appends_jsonl_csv_and_excludes_bonus_from_base_summary(self) -> None:
        with TemporaryDirectory() as directory:
            store = RewardStore(Path(directory))
            store.append(record("base", "none"))
            store.append(record("bonus", "chest"))
            self.assertEqual(len(store.read_all()), 2)
            self.assertEqual(
                store.read_all()[0]["context_evidence"],
                ["combat_text:紧急作战"],
            )
            with store.csv_path.open(
                encoding="utf-8-sig",
                newline="",
            ) as stream:
                rows = list(csv.DictReader(stream))
                self.assertEqual(len(rows), 2)
                self.assertEqual(
                    rows[0]["detected_combat_context"],
                    "emergency_combat",
                )
                self.assertEqual(
                    rows[0]["context_evidence"],
                    "combat_text:紧急作战",
                )
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

    def test_correct_combat_context_rebuilds_outputs(self) -> None:
        with TemporaryDirectory() as directory:
            store = RewardStore(Path(directory))
            original = record("base", "none")
            store.append(original)
            backup = store.correct_combat_context(
                original.sample_id,
                "combat",
                "人工确认普通作战",
            )
            self.assertTrue(backup.exists())
            payload = store.read_all()[0]
            self.assertEqual(payload["combat_context"], "combat")
            self.assertIn(
                "人工确认普通作战",
                payload["reviewer_notes"],
            )
            summary = json.loads(
                store.summary_path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                summary["groups"][0]["combat_context"],
                "combat",
            )

    def test_correct_parts_breakdown_keeps_base_summary_clean(self) -> None:
        with TemporaryDirectory() as directory:
            store = RewardStore(Path(directory))
            original = record("base", "none")
            store.append(original)
            backup = store.correct_parts_breakdown(
                original.sample_id,
                parts=1,
                bonus_parts=3,
                details="囊中骨 +3",
                note="人工拆分零件来源",
            )
            self.assertTrue(backup.exists())
            payload = store.read_all()[0]
            self.assertEqual(payload["parts"], 1)
            self.assertEqual(payload["bonus_parts"], 3)
            self.assertEqual(payload["parts_total"], 4)
            self.assertEqual(
                payload["parts_bonus_details"],
                "囊中骨 +3",
            )
            summary = json.loads(
                store.summary_path.read_text(encoding="utf-8")
            )
            group = summary["groups"][0]
            self.assertEqual(group["mean_parts"], 1.0)
            self.assertEqual(group["mean_bonus_parts"], 3.0)
        self.assertEqual(group["mean_total_parts"], 4.0)

    def test_correct_reward_counts_rebuilds_outputs(self) -> None:
        with TemporaryDirectory() as directory:
            store = RewardStore(Path(directory))
            store.append(record("sample-1", "none"))
            backup = store.correct_reward_counts(
                "sample-1",
                recruitment_tickets=2,
                parts=2,
                note="人工复核补记",
            )
            self.assertTrue(backup.exists())
            corrected = store.read_all()[0]
            self.assertEqual(corrected["recruitment_tickets"], 2)
            self.assertEqual(corrected["parts"], 2)
            self.assertEqual(corrected["parts_total"], 2)
            self.assertIn(
                "人工复核补记",
                corrected["reviewer_notes"],
            )


if __name__ == "__main__":
    unittest.main()
