from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import fmean
from typing import Any

from .models import RewardRecord


CSV_COLUMNS = (
    "sample_id",
    "captured_at",
    "source_floor",
    "location_context",
    "combat_context",
    "stage_name",
    "command_xp",
    "originium_ingots",
    "hope",
    "recruitment_tickets",
    "collectibles",
    "parts",
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
        records = self.read_all()
        self._write_csv(records)
        self._write_summary(records)

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
                for key in (
                    "displayed_reward_names",
                    "settlement_screenshots",
                    "reward_screenshots",
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
                values = [
                    float(sample[field])
                    for sample in samples
                    if sample.get(field) is not None
                ]
                return round(fmean(values), 4) if values else None

            summary.append(
                {
                    "source_floor": key[0],
                    "location_context": key[1],
                    "combat_context": key[2],
                    "sample_count": len(samples),
                    "mean_command_xp": mean("command_xp"),
                    "mean_originium_ingots": mean("originium_ingots"),
                    "mean_hope": mean("hope"),
                    "mean_recruitment_tickets": mean(
                        "recruitment_tickets"
                    ),
                    "mean_collectibles": mean("collectibles"),
                    "mean_parts": mean("parts"),
                }
            )
        self.summary_path.write_text(
            json.dumps(
                {
                    "schema_version": "0.1.0",
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

