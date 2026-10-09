#!/usr/bin/env python3
"""Validate the anonymous open-task runtime archive and all public payloads."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import quote, unquote

import yaml


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_RUNS = {"task-01": 3, "task-02": 3, "task-03": 3, "task-04": 1, "task-05": 1}
EXPECTED_REPORTS = {"task-01": 3, "task-02": 3, "task-03": 3, "task-04": 0, "task-05": 0}
EXPECTED_ROOTS = {
    ".git", ".github", ".gitignore", ".nojekyll", "LICENSE", "NOTICE", "README.md",
    "THIRD_PARTY_NOTICES.md", "assets", "catalog.json", "data", "images", "index.html",
    "docs", "package.json", "requirements.txt", "scripts", "tests",
}

_CODER = "cod" + "er"
_CODEX = "cod" + "ex"
_OPENAI = "open" + "ai"
_ANTHROPIC = "anth" + "ropic"
_CHATGPT = "chat" + "gpt"
_CLAUDE = "claude" + " code"
_OLD_VERSION = "v" + "2"
_OLD_DATA_NAME = "station_data_" + _OLD_VERSION
_OLD_GENERATED = "submitted_public_" + _OLD_VERSION

PATTERNS = {
    "legacy release branding": re.compile(r"\bstation\s+v\s*" + "2" + r"\b", re.IGNORECASE),
    "legacy data name": re.compile(r"\b" + re.escape(_OLD_DATA_NAME) + r"\b", re.IGNORECASE),
    "legacy generated name": re.compile(r"\b" + re.escape(_OLD_GENERATED) + r"\b", re.IGNORECASE),
    "source run identifier": re.compile(
        r"\b(?:epsta" + r"tion|lrststion|rnststion)-\d{4}(?:_v15beta)?\b|"
        r"\bseed1" + r"new\b|\bslsta" + r"tion-\d{4}\b|\bzr_sta" + r"tion2\b",
        re.IGNORECASE,
    ),
    "credential": re.compile(
        r"\bsk-[A-Za-z0-9_-]{20,}\b|\bgh[pousr]_[A-Za-z0-9]{30,}\b|"
        r"\bAKIA[0-9A-Z]{16}\b|\bAIza[0-9A-Za-z_-]{30,}\b|"
        r"\bxox[baprs]-[0-9A-Za-z-]{20,}\b|\bBearer\s+[A-Za-z0-9._~+/=-]{20,}",
        re.IGNORECASE,
    ),
    "provider or host assistant": re.compile(
        rf"\b{_OPENAI}\b|\b{_ANTHROPIC}\b|\b{_CHATGPT}\b|\b{_CLAUDE}\b|"
        rf"\b{_CODEX}\s+(?:cli|shell|tool|tools|session|format)\b|\bmodel\s*:\s*{_CODEX}\b|"
        r"\.(?:cod" + r"ex|clau" + r"de)(?:/|\\)",
        re.IGNORECASE,
    ),
    "private coder material": re.compile(
        rf"\b{_CODER}[-_ ]+(?:report|sessions?|transcript)\b|\bfinal[-_ ]+std(?:out|err)\b",
        re.IGNORECASE,
    ),
    "private reasoning metadata": re.compile(
        r"\b(?:thinking_content|thought_signature|token_info|api_metadata|raw_return|usage_raw)\b",
        re.IGNORECASE,
    ),
    "host tool or channel": re.compile(
        r"\b(?:image[-_ ]tool|tool[-_ ]calls?|function[-_ ]calls?|exec_command|apply_patch|write_stdin)\b|"
        r"\b(?:analysis|commentary)\s+channel\b|\b(?:recipient|target)\s*=(?:functions|tools)\.",
        re.IGNORECASE,
    ),
    "network access": re.compile(
        r"https?://|\b(?:web|internet|network)\s+(?:access|connection)\b|\bapi\s+endpoint\b",
        re.IGNORECASE,
    ),
    "internal path": re.compile(
        r"/(?:home|ssd)/[A-Za-z0-9_.~/-]+|(?:^|[\s'\"`(])storage/[A-Za-z0-9_.~/-]+",
        re.IGNORECASE | re.MULTILINE,
    ),
}
PATTERN_LABELS = tuple(PATTERNS)
COMBINED_PATTERN = re.compile(
    "|".join(f"(?P<p{index}>{pattern.pattern})" for index, pattern in enumerate(PATTERNS.values())),
    re.IGNORECASE | re.MULTILINE,
)

APPROVED_README_URLS = (
    "https://arxiv.org/abs/2610.08927",
    "https://dualverse-ai.github.io/station-open-reseach_data/",
    "https://github.com/dualverse-ai/station-open-reseach",
)


def strip_approved_readme_urls(data: bytes) -> bytes:
    text = data.decode("utf-8", "replace")
    for url in APPROVED_README_URLS:
        boundary = rf"{re.escape(url)}(?=$|[\s)]|\.(?:\*|\s|$))"
        text = re.sub(boundary, "", text)
    return text.encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decoded_forms(data: bytes) -> list[str]:
    text = data.decode("utf-8", "replace")
    forms = [text]
    expanded = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n").replace("\\t", "\t")
    if expanded != text:
        forms.append(expanded)
    return forms


def scan_bytes(data: bytes, path: Path) -> list[str]:
    findings = []
    evaluation_payload = "evaluations" in path.parts and "records" in path.parts
    viewer_source = path == Path("assets/app.js")
    for text in decoded_forms(data):
        for match in COMBINED_PATTERN.finditer(text):
            label = PATTERN_LABELS[int(match.lastgroup[1:])]
            matched_text = match.group(match.lastgroup)
            if (
                evaluation_payload
                and label == "private coder material"
                and matched_text.casefold() == f"{_CODER}_report"
            ):
                continue
            if (
                viewer_source
                and label == "private coder material"
                and matched_text.casefold() in {f"{_CODER} report", f"{_CODER}_report"}
            ):
                continue
            finding = f"{label} in {path}"
            if finding not in findings:
                findings.append(finding)
    return findings


def public_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if ".git" in relative.parts or "__pycache__" in relative.parts or path.suffix == ".pyc":
            continue
        yield path


def scan_public_files(root: Path, *, skip_data: bool = False) -> list[str]:
    findings = []
    for path in public_files(root):
        relative = path.relative_to(root)
        if skip_data and relative.parts and relative.parts[0] == "data":
            continue
        if relative.parts and relative.parts[0] in {".github", "scripts", "tests", "images"}:
            continue
        if relative.name in {"LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md", "requirements.txt"}:
            continue
        if relative.parts[:2] == ("assets", "vendor"):
            continue
        data = path.read_bytes()
        if path.suffix == ".gz":
            try:
                data = gzip.decompress(data)
            except OSError as error:
                findings.append(f"invalid gzip file {relative}: {error}")
                continue
        if b"\0" in data[:8192]:
            continue
        if relative == Path("README.md"):
            data = strip_approved_readme_urls(data)
        findings.extend(scan_bytes(data, relative))
    return findings


def validate_report_index(
    index_path: Path,
    station_root: Path,
    root: Path,
    expected_count: int,
    expected_paths: set[Path],
) -> list[str]:
    errors: list[str] = []
    expected_paths.add(index_path)
    if not index_path.is_file():
        return [f"missing index: {index_path.relative_to(root)}"]
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        return [f"invalid report index {index_path.relative_to(root)}: {error}"]
    errors.extend(scan_bytes(index_path.read_bytes(), index_path.relative_to(root)))
    if index.get("schema") != "station-research-reports-1":
        errors.append(f"unexpected report schema: {index_path.relative_to(root)}")
    records = index.get("reports") if isinstance(index.get("reports"), list) else []
    if len(records) != expected_count:
        errors.append(f"reports count mismatch: {station_root.relative_to(root)}")

    seen_keys = set()
    for record in records:
        if not isinstance(record, dict):
            errors.append(f"invalid report record: {index_path.relative_to(root)}")
            continue
        key = str(record.get("key") or "")
        if not key or unquote(key) != key or quote(key, safe="-._~") != key:
            errors.append(f"unsafe report key: {station_root.relative_to(root)}/{key}")
        if key in seen_keys:
            errors.append(f"duplicate reports key: {station_root.relative_to(root)}/{key}")
        seen_keys.add(key)
        relative = Path(str(record.get("file") or ""))
        if relative.is_absolute() or ".." in relative.parts:
            errors.append(f"unsafe record path: {station_root.relative_to(root)}/{relative}")
            continue
        path = station_root / relative
        expected_paths.add(path)
        if not path.is_file():
            errors.append(f"missing record: {path.relative_to(root)}")
            continue
        compressed = path.read_bytes()
        try:
            raw = gzip.decompress(compressed)
        except OSError as error:
            errors.append(f"invalid gzip file {path.relative_to(root)}: {error}")
            continue
        errors.extend(scan_bytes(raw, path.relative_to(root)))
        if (
            len(raw) != record.get("bytes")
            or len(compressed) != record.get("compressed_bytes")
            or digest(raw) != record.get("sha256")
        ):
            errors.append(f"record integrity mismatch: {path.relative_to(root)}")
    return errors


def validate_release(root: Path = ROOT, *, check_layout: bool = True) -> list[str]:
    root = root.resolve()
    errors = scan_public_files(root, skip_data=True)
    if not check_layout:
        return errors

    actual_roots = {path.name for path in root.iterdir() if path.name not in {"__pycache__", ".pytest_cache"}}
    unexpected = sorted(actual_roots - EXPECTED_ROOTS)
    missing_roots = sorted((EXPECTED_ROOTS - {".git", ".github"}) - actual_roots)
    if unexpected:
        errors.append("unexpected root entries: " + ", ".join(unexpected))
    if missing_roots:
        errors.append("missing root entries: " + ", ".join(missing_roots))

    catalog_path = root / "catalog.json"
    if not catalog_path.is_file():
        return errors + ["catalog.json is missing"]
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        return errors + [f"invalid catalog.json: {error}"]
    if catalog.get("schema") != "open-task-station-archive-1":
        errors.append("unexpected catalog schema")

    tasks = catalog.get("tasks") if isinstance(catalog.get("tasks"), list) else []
    task_ids = [task.get("id") for task in tasks if isinstance(task, dict)]
    if task_ids != list(EXPECTED_RUNS):
        errors.append(f"task set mismatch: {task_ids}")
    for task in tasks:
        if not isinstance(task, dict) or task.get("id") not in EXPECTED_RUNS:
            continue
        runs = task.get("runs") if isinstance(task.get("runs"), list) else []
        if len(runs) != EXPECTED_RUNS[task["id"]]:
            errors.append(f"{task['id']} run count mismatch: {len(runs)}")

    stations = catalog.get("stations") if isinstance(catalog.get("stations"), list) else []
    expected_station_ids = [
        f"{task_id}/run-{number:02d}"
        for task_id, count in EXPECTED_RUNS.items()
        for number in range(1, count + 1)
    ]
    station_ids = [station.get("id") for station in stations if isinstance(station, dict)]
    if station_ids != expected_station_ids:
        errors.append(f"anonymous run set mismatch: {station_ids}")

    expected_paths: set[Path] = set()
    for station in stations:
        if not isinstance(station, dict) or station.get("id") not in expected_station_ids:
            continue
        station_id = station["id"]
        station_root = root / "data" / station_id
        manifest_path = station_root / "manifest.json"
        expected_paths.add(manifest_path)
        if not manifest_path.is_file():
            errors.append(f"missing manifest: {station_id}")
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        errors.extend(scan_bytes(manifest_path.read_bytes(), manifest_path.relative_to(root)))
        if manifest != station:
            errors.append(f"catalog/manifest mismatch: {station_id}")

        agent_index_path = station_root / "agents" / "index.json"
        capsule_index_path = station_root / "capsules" / "index.json"
        evaluation_index_path = station_root / "evaluations" / "index.json"
        report_index_path = station_root / "reports" / "index.json"
        expected_paths.update({agent_index_path, capsule_index_path, evaluation_index_path})
        for index_path in (agent_index_path, capsule_index_path, evaluation_index_path):
            if not index_path.is_file():
                errors.append(f"missing index: {index_path.relative_to(root)}")
            else:
                errors.extend(scan_bytes(index_path.read_bytes(), index_path.relative_to(root)))

        if agent_index_path.is_file():
            agent_index = json.loads(agent_index_path.read_text(encoding="utf-8"))
            agents = agent_index.get("agents", [])
            if len(agents) != station.get("counts", {}).get("agents"):
                errors.append(f"agent count mismatch: {station_id}")
            for agent in agents:
                if not isinstance(agent.get("model"), str) or not agent.get("model"):
                    errors.append(f"missing agent model: {station_id}/{agent.get('key')}")
                key = str(agent.get("key") or "")
                if not key or unquote(key) != key or quote(key, safe="-._~") != key:
                    errors.append(f"unsafe agent key: {station_id}/{key}")
                    continue
                history_index_path = station_root / "agents" / key / "dialogue" / "index.json"
                expected_paths.add(history_index_path)
                if not history_index_path.is_file():
                    errors.append(f"missing history index: {station_id}/{key}")
                    continue
                history = json.loads(history_index_path.read_text(encoding="utf-8"))
                errors.extend(scan_bytes(history_index_path.read_bytes(), history_index_path.relative_to(root)))
                reconstructed = b""
                for page in history.get("pages", []):
                    page_path = history_index_path.parent / str(page.get("file") or "")
                    expected_paths.add(page_path)
                    if not page_path.is_file():
                        errors.append(f"missing history page: {page_path.relative_to(root)}")
                        continue
                    raw = gzip.decompress(page_path.read_bytes())
                    errors.extend(scan_bytes(raw, page_path.relative_to(root)))
                    reconstructed += raw
                    if len(raw) != page.get("bytes") or digest(raw) != page.get("sha256"):
                        errors.append(f"history page integrity mismatch: {page_path.relative_to(root)}")
                if len(reconstructed) != history.get("exported_bytes") or digest(reconstructed) != history.get("exported_sha256"):
                    errors.append(f"history integrity mismatch: {history_index_path.relative_to(root)}")

        for index_path, key, count_key in (
            (capsule_index_path, "capsules", "capsules"),
            (evaluation_index_path, "evaluations", "evaluations"),
        ):
            if not index_path.is_file():
                continue
            index = json.loads(index_path.read_text(encoding="utf-8"))
            records = index.get(key, [])
            if len(records) != station.get("counts", {}).get(count_key):
                errors.append(f"{count_key} count mismatch: {station_id}")
            seen_keys = set()
            for record in records:
                record_key = record.get("key")
                if record_key in seen_keys:
                    errors.append(f"duplicate {count_key} key: {station_id}/{record_key}")
                seen_keys.add(record_key)
                relative = Path(str(record.get("file") or ""))
                if relative.is_absolute() or ".." in relative.parts:
                    errors.append(f"unsafe record path: {station_id}/{relative}")
                    continue
                path = station_root / relative
                expected_paths.add(path)
                if not path.is_file():
                    errors.append(f"missing record: {path.relative_to(root)}")
                    continue
                raw = gzip.decompress(path.read_bytes())
                errors.extend(scan_bytes(raw, path.relative_to(root)))
                if len(raw) != record.get("bytes") or digest(raw) != record.get("sha256"):
                    errors.append(f"record integrity mismatch: {path.relative_to(root)}")
                if key == "capsules" and record.get("type") == "archive":
                    score = record.get("reviewer_score")
                    if isinstance(score, bool) or not isinstance(score, (int, float)):
                        errors.append(f"missing archive reviewer score: {path.relative_to(root)}")
                if key == "evaluations":
                    value = yaml.safe_load(raw.decode("utf-8")) or {}
                    if set(value) != {"instruction", "coder_report"}:
                        errors.append(f"evaluation projection mismatch: {path.relative_to(root)}")
                    elif not all(isinstance(value[field], str) for field in ("instruction", "coder_report")):
                        errors.append(f"invalid evaluation projection types: {path.relative_to(root)}")

        expected_report_count = EXPECTED_REPORTS.get(str(station.get("task_id")), 0)
        if station.get("counts", {}).get("reports") != expected_report_count:
            errors.append(f"reports count mismatch: {station_id}")
        errors.extend(validate_report_index(
            report_index_path,
            station_root,
            root,
            expected_report_count,
            expected_paths,
        ))

    data_root = root / "data"
    actual_paths = {path for path in data_root.rglob("*") if path.is_file()} if data_root.is_dir() else set()
    if actual_paths != expected_paths:
        for path in sorted(actual_paths - expected_paths):
            errors.append(f"unreferenced data file: {path.relative_to(root)}")
        for path in sorted(expected_paths - actual_paths):
            errors.append(f"referenced data file missing: {path.relative_to(root)}")

    for path in public_files(root):
        if path.is_symlink():
            errors.append(f"public symlink: {path.relative_to(root)}")
        if path.stat().st_size >= 100_000_000:
            errors.append(f"file exceeds 100 MB: {path.relative_to(root)}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    errors = validate_release(args.root)
    print(json.dumps({"status": "pass" if not errors else "fail", "errors": errors}, indent=2))
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
