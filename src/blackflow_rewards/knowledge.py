from __future__ import annotations


# Immediate part-box increases caused by receiving a collectible. These are
# recorded separately from the node's own part reward.
KNOWN_COLLECTIBLE_PART_GRANTS: dict[str, int] = {
    "囊中骨": 3,
}


# Only fixed node-specific stages belong here. Normal and emergency variants
# often share stage names, so they must continue to rely on UI context.
KNOWN_STAGE_CONTEXTS: dict[str, str] = {
    "共斗": "encounter",
}
