"""Secretary addon — Claude-supervised heavy-lifting assistant for MMV Large.

Purpose: take over token-intensive read/aggregate/summarize work so the
supervising Claude session reads compact digests instead of raw output.

Active MMV Large release is pinned by
`operate-fr-bench/releases/large/current.yaml`. See addons.secretary.release
for the loader.

Governed-config writes (pattern_library, prefix doctrine, freeze notes)
remain proposal-only via src.secretary.secretary_core.ProposalStore. This
addon performs only read/explore/aggregate work; it does not mutate
governed surfaces.
"""
