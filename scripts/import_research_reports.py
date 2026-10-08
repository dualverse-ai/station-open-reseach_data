#!/usr/bin/env python3
"""Import sanitized tick-300 research reports into the static archive."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from export_open_tasks import ROOT, parse_source_map, sanitize_text, write_gzip, write_json


def report_title(markdown: str) -> str:
    match = re.search(r"(?m)^#[ \t]+(.+?)[ \t]*$", markdown)
    if not match:
        raise ValueError("Research report has no level-one title")
    return match.group(1)


def source_reports(source: Path) -> list[Path]:
    direct_runs = sorted(
        (path for path in source.glob("direct_*") if path.is_dir()),
        key=lambda path: path.name.casefold(),
    )
    papers = [path / "draft" / "research_paper.md" for path in direct_runs]
    if len(papers) != 3 or not all(path.is_file() for path in papers):
        raise ValueError(f"{source} must contain exactly 3 research reports")
    return papers


def import_reports(
    source_root: Path,
    release_root: Path = ROOT,
    source_map: dict[str, Path] | None = None,
) -> dict[str, int]:
    if source_map is None:
        raise ValueError("Research report import requires explicit source mappings")
    source_root = source_root.resolve()
    release_root = release_root.resolve()
    catalog_path = release_root / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    stations = catalog.get("stations") if isinstance(catalog.get("stations"), list) else []
    stations_by_id = {
        str(station.get("id")): station
        for station in stations
        if isinstance(station, dict) and station.get("id")
    }
    unknown_stations = sorted(set(source_map) - set(stations_by_id))
    if unknown_stations:
        raise ValueError("Report mapping contains unknown stations: " + ", ".join(unknown_stations))

    imported_stations = imported_reports = 0
    for station_id, station in stations_by_id.items():
        station_root = release_root / "data" / station_id
        reports_root = station_root / "reports"
        if reports_root.exists():
            shutil.rmtree(reports_root)

        records = []
        relative_source = source_map.get(station_id)
        if relative_source is not None:
            for number, paper_path in enumerate(source_reports(source_root / relative_source), start=1):
                markdown = sanitize_text(paper_path.read_text(encoding="utf-8")) + "\n"
                raw = markdown.encode("utf-8")
                key = f"report-{number:02d}"
                output = reports_root / "records" / f"{key}.md.gz"
                records.append({
                    "id": key,
                    "key": key,
                    "title": report_title(markdown),
                    "file": output.relative_to(station_root).as_posix(),
                    **write_gzip(output, raw),
                })
            imported_stations += 1
            imported_reports += len(records)

        write_json(reports_root / "index.json", {
            "schema": "station-research-reports-1",
            "reports": records,
        })
        counts = station.setdefault("counts", {})
        counts["reports"] = len(records)
        write_json(station_root / "manifest.json", station)

    station_counts = {
        station_id: dict(station.get("counts") or {})
        for station_id, station in stations_by_id.items()
    }
    for task in catalog.get("tasks", []):
        if not isinstance(task, dict):
            continue
        for run in task.get("runs", []):
            if isinstance(run, dict) and run.get("station_id") in station_counts:
                run["counts"] = station_counts[str(run["station_id"])]

    scope = catalog.get("scope")
    if isinstance(scope, dict):
        scope["included"] = (
            "Agent dialogue, capsule records, research-submission evaluations, and final research reports "
            "from archived Station runs."
        )

    write_json(catalog_path, catalog)
    return {"stations": imported_stations, "reports": imported_reports}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", type=Path, help="Directory containing tick-300 report groups")
    parser.add_argument("--release-root", type=Path, default=ROOT)
    parser.add_argument(
        "--map",
        dest="source_maps",
        action="append",
        required=True,
        metavar="STATION_ID=RELATIVE_PATH",
        help="Map an anonymous run to a report group relative to source_root; repeat per run",
    )
    args = parser.parse_args()
    result = import_reports(args.source_root, args.release_root, parse_source_map(args.source_maps))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
