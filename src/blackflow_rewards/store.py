from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
import shutil
from statistics import fmean
from typing import Any

from .models import COMBAT_CONTEXTS, RewardRecord


CSV_COLUMNS = (
    "sample_id",
    "captured_at",
    "source_floor",
    "location_context",
    "combat_context",
    "detected_combat_context",
    "context_evidence",
    "stage_name",
    "command_xp",
    "originium_ingots",
    "normal_reward_ingots",
    "unowned_wealth_ingots",
    "hope",
    "recruitment_tickets",
    "collectibles",
    "parts",
    "bonus_parts",
    "parts_total",
    "parts_bonus_details",
    "bonus_source",
    "bonus_details",
    "command_xp_multiplier",
    "ingot_multiplier",
    "displayed_reward_names",
    "settlement_screenshots",
    "reward_screenshots",
    "reviewer_notes",
    "review_status",
    "eligible_for_base_statistics",
)


class RewardStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = root / "rewards.jsonl"
        self.csv_path = root / "rewards.csv"
        self.summary_path = root / "summary.json"

    def append(self, record: RewardRecord) -> None:
        payload = record.to_dict()
        with self.jsonl_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.rebuild_outputs()

    def rebuild_outputs(self) -> None:
        records = self.read_all()
        self._write_csv(records)
        self._write_summary(records)

    def correct_combat_context(
        self,
        sample_id: str,
        combat_context: str,
        note: str = "",
    ) -> Path:
        valid_contexts = {item_id for item_id, _ in COMBAT_CONTEXTS}
        if combat_context not in valid_contexts:
            raise ValueError(f"未知战斗类型：{combat_context}")
        records = self.read_all()
        matches = [
            payload
            for payload in records
            if payload.get("sample_id") == sample_id
        ]
        if len(matches) != 1:
            raise ValueError(
                f"样本必须唯一存在，实际找到 {len(matches)} 条：{sample_id}"
            )
        payload = matches[0]
        payload["combat_context"] = combat_context
        if note:
            old_notes = str(payload.get("reviewer_notes", "")).strip()
            payload["reviewer_notes"] = (
                f"{old_notes}；{note}" if old_notes else note
            )
        return self._replace_records(records)

    def correct_parts_breakdown(
        self,
        sample_id: str,
        parts: int,
        bonus_parts: int,
        details: str = "",
        note: str = "",
    ) -> Path:
        if parts < 0 or bonus_parts < 0:
            raise ValueError("零件数量不能为负数")
        records = self.read_all()
        matches = [
            payload
            for payload in records
            if payload.get("sample_id") == sample_id
        ]
        if len(matches) != 1:
            raise ValueError(
                f"样本必须唯一存在，实际找到 {len(matches)} 条：{sample_id}"
            )
        payload = matches[0]
        payload["parts"] = parts
        payload["bonus_parts"] = bonus_parts
        payload["parts_total"] = parts + bonus_parts
        payload["parts_bonus_details"] = details
        payload["schema_version"] = "0.3.0"
        if note:
            old_notes = str(payload.get("reviewer_notes", "")).strip()
            payload["reviewer_notes"] = (
                f"{old_notes}；{note}" if old_notes else note
            )
        return self._replace_records(records)

    def correct_reward_counts(
        self,
        sample_id: str,
        recruitment_tickets: int | None = None,
        parts: int | None = None,
        note: str = "",
    ) -> Path:
        if recruitment_tickets is None and parts is None:
            raise ValueError("at least one reward count is required")
        if recruitment_tickets is not None and recruitment_tickets < 0:
            raise ValueError("recruitment ticket count cannot be negative")
        if parts is not None and parts < 0:
            raise ValueError("part count cannot be negative")
        records = self.read_all()
        matches = [
            payload
            for payload in records
            if payload.get("sample_id") == sample_id
        ]
        if len(matches) != 1:
            raise ValueError(
                f"sample must exist exactly once; found "
                f"{len(matches)}: {sample_id}"
            )
        payload = matches[0]
        if recruitment_tickets is not None:
            payload["recruitment_tickets"] = recruitment_tickets
        if parts is not None:
            payload["parts"] = parts
            bonus_parts = int(payload.get("bonus_parts") or 0)
            payload["parts_total"] = parts + bonus_parts
        payload["schema_version"] = "0.3.0"
        if note:
            old_notes = str(payload.get("reviewer_notes", "")).strip()
            payload["reviewer_notes"] = (
                f"{old_notes}；{note}" if old_notes else note
            )
        return self._replace_records(records)

    def _replace_records(
        self,
        records: list[dict[str, Any]],
    ) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        backup_path = self.jsonl_path.with_name(
            f"{self.jsonl_path.name}.{timestamp}.bak"
        )
        shutil.copy2(self.jsonl_path, backup_path)
        replacement_path = self.jsonl_path.with_suffix(".jsonl.tmp")
        replacement_path.write_text(
            "".join(
                json.dumps(item, ensure_ascii=False) + "\n"
                for item in records
            ),
            encoding="utf-8",
        )
        replacement_path.replace(self.jsonl_path)
        self.rebuild_outputs()
        return backup_path

    def read_all(self) -> list[dict[str, Any]]:
        if not self.jsonl_path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in self.jsonl_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
        return records

    def _write_csv(self, records: list[dict[str, Any]]) -> None:
        with self.csv_path.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for payload in records:
                row = {key: payload.get(key, "") for key in CSV_COLUMNS}
                if row["bonus_parts"] == "":
                    row["bonus_parts"] = 0
                if row["parts_total"] == "":
                    row["parts_total"] = payload.get("parts", 0)
                for key in (
                    "displayed_reward_names",
                    "settlement_screenshots",
                    "reward_screenshots",
                    "context_evidence",
                ):
                    value = row[key]
                    if isinstance(value, list):
                        row[key] = " | ".join(str(item) for item in value)
                writer.writerow(row)

    def _write_summary(self, records: list[dict[str, Any]]) -> None:
        groups: dict[tuple[str, str, str], list[dict[str, Any]]] = (
            defaultdict(list)
        )
        for payload in records:
            if not payload.get("eligible_for_base_statistics"):
                continue
            key = (
                str(payload.get("source_floor", "")),
                str(payload.get("location_context", "")),
                str(payload.get("combat_context", "")),
            )
            groups[key].append(payload)
        summary: list[dict[str, Any]] = []
        for key, samples in sorted(groups.items()):
            def mean(field: str) -> float | None:
                values: list[float] = []
                for sample in samples:
                    value = sample.get(field)
                    if field == "bonus_parts" and value is None:
                        value = 0
                    if field == "parts_total" and value is None:
                        value = sample.get("parts")
                    if value is not None:
                        values.append(float(value))
                return round(fmean(values), 4) if values else None

            summary.append(
                {
                    "source_floor": key[0],
                    "location_context": key[1],
                    "combat_context": key[2],
                    "sample_count": len(samples),
                    "mean_command_xp": mean("command_xp"),
                    "mean_originium_ingots": mean("originium_ingots"),
                    "mean_normal_reward_ingots": mean(
                        "normal_reward_ingots"
                    ),
                    "mean_unowned_wealth_ingots": mean(
                        "unowned_wealth_ingots"
                    ),
                    "mean_hope": mean("hope"),
                    "mean_recruitment_tickets": mean(
                        "recruitment_tickets"
                    ),
                    "mean_collectibles": mean("collectibles"),
                    "mean_parts": mean("parts"),
                    "mean_bonus_parts": mean("bonus_parts"),
                    "mean_total_parts": mean("parts_total"),
                }
            )
        self.summary_path.write_text(
            json.dumps(
                {
                    "schema_version": "0.3.0",
                    "eligible_sample_count": sum(
                        len(samples) for samples in groups.values()
                    ),
                    "groups": summary,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
