#!/usr/bin/env python3
"""Backfill public Agent indexes from private snapshot model metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from export_open_tasks import ROOT, parse_source_map, safe_mapping, sanitize_text, write_json


def metadata_models(source: Path) -> dict[str, str]:
    models: dict[str, str] = {}
    agents = source / "agents"
    if not agents.is_dir():
        raise FileNotFoundError(agents)
    for metadata_path in sorted(agents.glob("*.yaml"), key=lambda path: path.name.casefold()):
        metadata = safe_mapping(metadata_path.read_bytes())
        name = str(metadata.get("agent_name") or metadata_path.stem)
        model = sanitize_text(str(metadata.get("model_name") or ""))
        if model:
            models[name] = model
    return models


def backfill_models(
    source_root: Path,
    release_root: Path = ROOT,
    source_map: dict[str, Path] | None = None,
) -> dict[str, int]:
    if source_map is None:
        raise ValueError("Agent model backfill requires explicit source mappings")
    source_root = source_root.resolve()
    release_root = release_root.resolve()
    station_count = agent_count = resolved_count = 0

    for index_path in sorted(release_root.glob("data/task-*/run-*/agents/index.json")):
        station_id = index_path.parents[1].relative_to(release_root / "data").as_posix()
        relative_source = source_map.get(station_id)
        models = metadata_models(source_root / relative_source) if relative_source is not None else {}
        index = json.loads(index_path.read_text(encoding="utf-8"))
        agents = index.get("agents") if isinstance(index.get("agents"), list) else []
        for agent in agents:
            if not isinstance(agent, dict):
                continue
            model = models.get(str(agent.get("name") or ""), "Unknown")
            agent["model"] = model
            agent_count += 1
            resolved_count += model != "Unknown"
        write_json(index_path, index)
        station_count += 1

    return {"stations": station_count, "agents": agent_count, "resolved": resolved_count}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", type=Path, help="Directory containing the private Station snapshots")
    parser.add_argument("--release-root", type=Path, default=ROOT)
    parser.add_argument(
        "--map",
        dest="source_maps",
        action="append",
        required=True,
        metavar="STATION_ID=RELATIVE_PATH",
        help="Map an anonymous run to a source path relative to source_root; repeat per run",
    )
    args = parser.parse_args()
    result = backfill_models(args.source_root, args.release_root, parse_source_map(args.source_maps))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
