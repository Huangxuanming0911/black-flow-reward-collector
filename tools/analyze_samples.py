from __future__ import annotations

import json
from pathlib import Path
import sys

from blackflow_rewards.images import read_image
from blackflow_rewards.vision import FrameAnalyzer


def main() -> int:
    paths = [Path(item) for item in sys.argv[1:]]
    if not paths:
        paths = sorted(Path("data/samples").glob("*.jpg"))
    analyzer = FrameAnalyzer()
    output = []
    for path in paths:
        image = read_image(path)
        result = analyzer.analyze(image)
        output.append(
            {
                "file": str(path),
                "kind": result.kind.value,
                "stage_name": result.stage_name,
                "battle_command_xp": result.battle_command_xp,
                "reward_ingots": result.reward_ingots,
                "normal_reward_ingots": result.normal_reward_ingots,
                "unowned_wealth_ingots": (
                    result.unowned_wealth_ingots
                ),
                "reward_tickets": result.reward_tickets,
                "visible_reward_names": result.visible_reward_names,
                "source_floor": result.source_floor,
                "location_context": result.location_context,
                "combat_context": result.combat_context,
                "context_evidence": result.context_evidence,
                "ocr_text": result.raw_text,
            }
        )
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
