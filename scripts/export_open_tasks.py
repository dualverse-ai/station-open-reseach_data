#!/usr/bin/env python3
"""Build an anonymous static archive from explicit Station runtime snapshots."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import yaml


ROOT = Path(__file__).resolve().parents[1]
PAGE_DOCUMENT_LIMIT = 20
PAGE_BYTE_TARGET = 512 * 1024

TASKS = (
    {"id": "task-01", "title": "Emergent Planning", "description": "Mechanistic analysis of planning in a trained Sokoban agent."},
    {"id": "task-02", "title": "Low-Rank Language-Model Analysis", "description": "Empirical analysis of low-rank structure in language-model logit tables."},
    {"id": "task-03", "title": "Recurrent Network Dynamics", "description": "Analysis of learned solutions in fixed-delay recurrent networks."},
    {"id": "task-04", "title": "Subliminal Learning", "description": "Mechanistic study of trait transmission through semantically unrelated data."},
    {"id": "task-05", "title": "Visual Hallucination", "description": "Analysis of content-based and knowledge-based hallucination in vision-language models."},
)
TASK_BY_ID = {item["id"]: item for item in TASKS}

PRIVATE_KEYS = {
    "api_metadata",
    "backend",
    "base_url",
    "coder",
    "coder_report",
    "coder_session",
    "notification",
    "provider",
    "raw_return",
    "reasoning_id",
    "response_id",
    "session_id",
    "thinking_content",
    "thought_signature",
    "token_info",
    "usage_raw",
}

_CODER = "cod" + "er"
_CODEX = "cod" + "ex"
_OPENAI = "open" + "ai"
_ANTHROPIC = "anth" + "ropic"
_CHATGPT = "chat" + "gpt"
_CLAUDE = "claude" + " code"
_FINAL_STDOUT = "final" + r"\s+std(?:out|err)"
_WEB_ACCESS = r"(?:web|internet|network)" + r"\s+(?:access|connection)"
_STORAGE_PATH = r"(?:^|[\s'\"`(])storage/[A-Za-z0-9_.~/-]+"

FORBIDDEN_LINE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"https?://",
        r"/(?:home|ssd)/[A-Za-z0-9_.~/-]+",
        _STORAGE_PATH,
        rf"\b{_CODER}[-_ ]+(?:report|sessions?|transcript)\b",
        rf"\b{_FINAL_STDOUT}\b",
        rf"\b{_OPENAI}\b|\b{_ANTHROPIC}\b|\b{_CHATGPT}\b|\b{_CLAUDE}\b",
        rf"\b{_CODEX}\s+(?:cli|shell|tool|tools|session|format)\b",
        rf"\bmodel\s*:\s*{_CODEX}\b",
        r"\.(?:cod" + r"ex|clau" + r"de)(?:/|\\)",
        _WEB_ACCESS,
        r"\b(?:image[-_ ]tool|tool[-_ ]calls?|function[-_ ]calls?)\b",
        r"\b(?:api[-_ ]?key|bearer\s+token|api\s+endpoint)\b",
        r"\b(?:thinking_content|thinking_text|thought_signature|token_info|api_metadata|raw_return|usage_raw)\b",
        r"\b(?:analysis|commentary)\s+channel\b",
        r"\b(?:recipient|target)\s*=(?:functions|tools)\.",
        r"\b(?:exec_command|apply_patch|write_stdin)\b",
        r"\bsk-[A-Za-z0-9_-]{20,}\b",
        r"\bgh[pousr]_[A-Za-z0-9]{30,}\b",
        r"\bAKIA[0-9A-Z]{16}\b",
        r"\bAIza[0-9A-Za-z_-]{30,}\b",
        r"\bxox[baprs]-[0-9A-Za-z-]{20,}\b",
    )
)

DROP_DOCUMENT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        rf"\b{_CODER}[-_ ]+(?:report|sessions?|transcript)\b",
        rf"\b{_OPENAI}\s+{_CODEX}\b",
        rf"\b{_CODEX}\s+(?:cli|shell|tool|tools|session|format)\b",
        r"\b(?:tool[-_ ]calls?|function[-_ ]calls?)\b",
    )
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def filesystem_key(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._~-]+", "-", name).strip("-.")[:48] or "record"
    return f"{slug}-{hashlib.sha1(name.encode()).hexdigest()[:10]}"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_gzip(path: Path, data: bytes) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    compressed = gzip.compress(data, compresslevel=6, mtime=0)
    path.write_bytes(compressed)
    return {"bytes": len(data), "compressed_bytes": len(compressed), "sha256": sha256(data)}


def safe_mapping(raw: bytes) -> dict[str, Any]:
    try:
        value = yaml.safe_load(raw.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError):
        return {}
    return value if isinstance(value, dict) else {}


def detect_task_id(research_task: str) -> str:
    normalized = re.sub(r"\s+", " ", research_task).casefold()
    rules = (
        ("task-01", ("emergent planning", "sokoban agent")),
        ("task-02", ("low-rank", "logit tables")),
        ("task-03", ("k-delay rnns", "recurrent network", "learned solutions in small k-delay")),
        ("task-04", ("subliminal learning", "trait transmission")),
        ("task-05", ("visual hallucination", "hallucination in lvlms")),
    )
    matches = [task_id for task_id, terms in rules if any(term in normalized for term in terms)]
    if len(matches) != 1:
        raise ValueError(f"Could not uniquely identify research task; matches={matches}")
    return matches[0]


def sanitize_text(value: str) -> str:
    lines = value.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t").splitlines()
    kept = [line for line in lines if not any(pattern.search(line) for pattern in FORBIDDEN_LINE_PATTERNS)]
    return "\n".join(kept).strip()


def sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        projected: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).casefold()
            if normalized in PRIVATE_KEYS or "api_key" in normalized or "access_token" in normalized:
                continue
            projected[str(key)] = sanitize_value(item)
        return projected
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, str):
        return sanitize_text(value)
    return value


def contains_drop_marker(value: Any) -> bool:
    rendered = yaml.safe_dump(value, sort_keys=False, allow_unicode=True)
    return any(pattern.search(rendered) for pattern in DROP_DOCUMENT_PATTERNS)


def project_dialogue(raw: bytes) -> bytes:
    try:
        documents = list(yaml.safe_load_all(raw.decode("utf-8")))
    except (UnicodeDecodeError, yaml.YAMLError):
        return b""
    public: list[dict[str, Any]] = []
    for document in documents:
        if not isinstance(document, dict):
            continue
        if str(document.get("role") or "").casefold() == "model" and contains_drop_marker(document):
            continue
        projected = sanitize_value(document)
        if isinstance(projected, dict):
            public.append(projected)
    return yaml.safe_dump_all(public, sort_keys=False, allow_unicode=True).encode("utf-8")


def project_evaluation(metadata: dict[str, Any]) -> bytes:
    final = metadata.get("final") if isinstance(metadata.get("final"), dict) else {}
    details = final.get("evaluation_details")
    if isinstance(details, str):
        result = details
    elif details in (None, {}, []):
        result = ""
    else:
        result = yaml.safe_dump(details, sort_keys=False, allow_unicode=True).rstrip()
    public = sanitize_value({"instruction": str(metadata.get("instruction") or ""), "result": result})
    return yaml.safe_dump(public, sort_keys=False, allow_unicode=True).encode("utf-8")


def serialize_capsule(raw: bytes) -> tuple[bytes, dict[str, Any]]:
    metadata = safe_mapping(raw)
    if metadata:
        projected = sanitize_value(metadata)
        return yaml.safe_dump(projected, sort_keys=False, allow_unicode=True).encode("utf-8"), metadata
    text = sanitize_text(raw.decode("utf-8", "replace"))
    return (text + ("\n" if text else "")).encode("utf-8"), {}


def active_messages(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    messages = metadata.get("messages") if isinstance(metadata.get("messages"), list) else []
    return [message for message in messages if isinstance(message, dict) and not message.get("is_deleted")]


def mail_recipients(metadata: dict[str, Any]) -> list[str]:
    recipients = metadata.get("recipients")
    if isinstance(recipients, list):
        return [sanitize_text(str(item)) for item in recipients if sanitize_text(str(item))]
    if isinstance(recipients, str) and sanitize_text(recipients):
        return [sanitize_text(recipients)]
    return []


def question_status(metadata: dict[str, Any]) -> str:
    status = str(metadata.get("question_status") or "pending").strip().casefold()
    return status if status in {"pending", "open", "redacted", "solved", "retired"} else "pending"


def history_documents(raw: bytes) -> list[bytes]:
    if not raw.strip():
        return []
    starts = [0, *(match.start() + 1 for match in re.finditer(rb"\n---[ \t]*\r?\n", raw)), len(raw)]
    return [raw[starts[index]:starts[index + 1]] for index in range(len(starts) - 1)]


def split_history(raw: bytes) -> list[bytes]:
    documents = history_documents(raw)
    pages: list[bytes] = []
    current: list[bytes] = []
    current_bytes = 0
    for document in documents:
        current.append(document)
        current_bytes += len(document)
        if len(current) >= PAGE_DOCUMENT_LIMIT or current_bytes >= PAGE_BYTE_TARGET:
            pages.append(b"".join(current))
            current, current_bytes = [], 0
    if current:
        pages.append(b"".join(current))
    return pages


def history_summary(raw: bytes) -> dict[str, Any]:
    ticks = [int(value) for value in re.findall(rb"(?m)^tick:[ \t]*(\d+)[ \t]*$", raw)]
    roles = [value.decode("utf-8", "replace").strip() for value in re.findall(rb"(?m)^role:[ \t]*([^\r\n]+)", raw)]
    return {
        "documents": max(len(ticks), len(roles)),
        "first_tick": min(ticks) if ticks else None,
        "last_tick": max(ticks) if ticks else None,
        "roles": sorted(set(roles)),
    }


def export_history(source: Path, destination: Path) -> dict[str, Any]:
    raw = source.read_bytes()
    projected = project_dialogue(raw)
    pages = []
    for index, page in enumerate(split_history(projected), start=1):
        filename = f"page-{index:04d}.yamll.gz"
        pages.append({"file": filename, **history_summary(page), **write_gzip(destination / filename, page)})
    manifest = {
        "format": "dialogue-yamll-public-1",
        "source_bytes": len(raw),
        "source_sha256": sha256(raw),
        "exported_bytes": len(projected),
        "exported_sha256": sha256(projected),
        "pages": pages,
    }
    write_json(destination / "index.json", manifest)
    return manifest


def export_agents(source: Path, destination: Path) -> list[dict[str, Any]]:
    records = []
    agents = source / "agents"
    for history_source in sorted(agents.glob("*/llm_chat_history.yamll"), key=lambda path: path.parent.name.casefold()):
        name = history_source.parent.name
        key = filesystem_key(name)
        metadata_path = agents / f"{name}.yaml"
        metadata = safe_mapping(metadata_path.read_bytes()) if metadata_path.is_file() else {}
        history = export_history(history_source, destination / "agents" / key / "dialogue")
        safe_metadata = sanitize_value(metadata)
        records.append({
            "name": sanitize_text(name),
            "key": key,
            "display_name": safe_metadata.get("agent_name") or sanitize_text(name),
            "status": safe_metadata.get("status") or "Unknown",
            "lineage": safe_metadata.get("lineage") or "",
            "generation": safe_metadata.get("generation"),
            "description": safe_metadata.get("description") or "",
            "tick_birth": safe_metadata.get("tick_birth"),
            "tick_exit": safe_metadata.get("tick_exit"),
            "history": {
                "pages": len(history["pages"]),
                "documents": sum(int(page["documents"]) for page in history["pages"]),
                "first_tick": next((page["first_tick"] for page in history["pages"] if page["first_tick"] is not None), None),
                "last_tick": next((page["last_tick"] for page in reversed(history["pages"]) if page["last_tick"] is not None), None),
            },
        })
    write_json(destination / "agents" / "index.json", {"agents": records})
    return records


def export_capsules(source: Path, destination: Path) -> tuple[list[dict[str, Any]], list[str]]:
    records = []
    capsule_root = source / "capsules"
    if capsule_root.is_dir():
        candidates = sorted(capsule_root.rglob("*"), key=lambda path: path.as_posix().casefold())
        for capsule_source in candidates:
            if not capsule_source.is_file() or capsule_source.name.endswith(".lock") or capsule_source.name == "_index.json":
                continue
            relative = capsule_source.relative_to(capsule_root)
            capsule_type = relative.parts[0] if len(relative.parts) > 1 else "other"
            public_raw, metadata = serialize_capsule(capsule_source.read_bytes())
            capsule_id = str(metadata.get("capsule_id") or capsule_source.stem)
            key = hashlib.sha1(relative.as_posix().encode()).hexdigest()[:16]
            output = destination / "capsules" / "records" / capsule_type / f"{key}.yaml.gz"
            safe_metadata = sanitize_value(metadata)
            record = {
                "id": sanitize_text(capsule_id),
                "key": key,
                "type": capsule_type,
                "title": safe_metadata.get("title") or sanitize_text(capsule_source.stem),
                "author": safe_metadata.get("author_name") or "Unknown",
                "lineage": safe_metadata.get("author_lineage") or safe_metadata.get("lineage") or "",
                "created_tick": safe_metadata.get("created_at_tick"),
                "updated_tick": safe_metadata.get("last_updated_at_tick"),
                "word_count": safe_metadata.get("word_count_total"),
                "tags": safe_metadata.get("tags") if isinstance(safe_metadata.get("tags"), list) else [],
                "deleted": bool(safe_metadata.get("is_deleted", False)),
                "file": output.relative_to(destination).as_posix(),
                **write_gzip(output, public_raw),
            }
            if capsule_type in {"public", "private", "mail", "question"}:
                record["reply_count"] = max(0, len(active_messages(metadata)) - 1)
            if capsule_type == "mail":
                record["recipients"] = mail_recipients(metadata)
            if capsule_type == "question":
                record.update({
                    "question_status": question_status(metadata),
                    "question_net_upvote": int(metadata.get("question_net_upvote") or 0),
                    "question_solved_by_message_id": metadata.get("question_solved_by_message_id"),
                })
            records.append(record)
    records.sort(key=lambda item: (str(item["type"]), item["created_tick"] or 0, str(item["id"])))
    types = sorted({str(record["type"]) for record in records})
    write_json(destination / "capsules" / "index.json", {"capsules": records, "types": types})
    return records, types


def export_evaluations(source: Path, destination: Path) -> list[dict[str, Any]]:
    records = []
    evaluation_root = source / "rooms" / "research" / "evaluations"
    if evaluation_root.is_dir():
        for evaluation_source in sorted(evaluation_root.glob("*.yaml"), key=lambda path: path.name.casefold()):
            if evaluation_source.name.endswith(".lock"):
                continue
            metadata = safe_mapping(evaluation_source.read_bytes())
            public_raw = project_evaluation(metadata)
            evaluation_id = str(metadata.get("id") or evaluation_source.stem)
            key = filesystem_key(evaluation_id)
            output = destination / "evaluations" / "records" / f"{key}.yaml.gz"
            final = metadata.get("final") if isinstance(metadata.get("final"), dict) else {}
            safe_metadata = sanitize_value(metadata)
            safe_final = sanitize_value(final)
            records.append({
                "id": sanitize_text(evaluation_id),
                "key": key,
                "title": safe_metadata.get("title") or f"Research submission {sanitize_text(evaluation_id)}",
                "author": safe_metadata.get("author") or "Unknown",
                "lineage": safe_metadata.get("lineage") or "",
                "submitted_tick": safe_metadata.get("submitted_tick"),
                "status": safe_final.get("status") or safe_metadata.get("status") or "Unknown",
                "score": safe_final.get("primary_score", "n.a."),
                "tags": safe_metadata.get("tags") if isinstance(safe_metadata.get("tags"), list) else [],
                "abstract": safe_metadata.get("abstract") or "",
                "file": output.relative_to(destination).as_posix(),
                **write_gzip(output, public_raw),
            })
    records.sort(key=lambda item: (item["submitted_tick"] or 0, str(item["id"])))
    write_json(destination / "evaluations" / "index.json", {"evaluations": records})
    return records


def source_identity(source: Path) -> str:
    task = (source / "rooms" / "research" / "research_task.md").read_bytes()
    config = (source / "station_config.yaml").read_bytes() if (source / "station_config.yaml").is_file() else b""
    agent_names = "\n".join(sorted(path.parent.name for path in (source / "agents").glob("*/llm_chat_history.yamll"))).encode()
    return sha256(task + b"\0" + config + b"\0" + agent_names)


def discover_sources(paths: Iterable[Path]) -> dict[str, list[Path]]:
    grouped: dict[str, list[tuple[str, Path]]] = defaultdict(list)
    seen: set[Path] = set()
    for value in paths:
        source = value.expanduser().resolve()
        if source in seen:
            raise ValueError(f"Duplicate source: {source}")
        seen.add(source)
        task_path = source / "rooms" / "research" / "research_task.md"
        if not task_path.is_file():
            raise FileNotFoundError(task_path)
        task_id = detect_task_id(task_path.read_text(encoding="utf-8"))
        grouped[task_id].append((source_identity(source), source))
    missing = sorted(set(TASK_BY_ID) - set(grouped))
    if missing:
        raise ValueError("Missing task sources: " + ", ".join(missing))
    return {task_id: [source for _, source in sorted(items)] for task_id, items in grouped.items()}


def export_run(task_id: str, run_number: int, source: Path, data_root: Path) -> dict[str, Any]:
    run_id = f"run-{run_number:02d}"
    station_id = f"{task_id}/{run_id}"
    destination = data_root / task_id / run_id
    config_path = source / "station_config.yaml"
    config = safe_mapping(config_path.read_bytes()) if config_path.is_file() else {}
    agents = export_agents(source, destination)
    capsules, capsule_types = export_capsules(source, destination)
    evaluations = export_evaluations(source, destination)
    task = TASK_BY_ID[task_id]
    manifest = {
        "id": station_id,
        "task_id": task_id,
        "run_id": run_id,
        "title": f"{task['title']} - Run {run_number}",
        "tick": config.get("current_tick"),
        "status": "Archived",
        "counts": {"agents": len(agents), "capsules": len(capsules), "evaluations": len(evaluations)},
        "capsule_types": capsule_types,
    }
    write_json(destination / "manifest.json", manifest)
    return manifest


def export_release(sources: Iterable[Path], output: Path = ROOT) -> dict[str, Any]:
    output = output.resolve()
    grouped = discover_sources(sources)
    data_root = output / "data"
    if data_root.exists():
        shutil.rmtree(data_root)
    data_root.mkdir(parents=True)
    stations = []
    task_records = []
    for task in TASKS:
        task_sources = grouped[task["id"]]
        runs = []
        for index, source in enumerate(task_sources, start=1):
            print(f"Exporting {task['id']}/run-{index:02d}", flush=True)
            manifest = export_run(task["id"], index, source, data_root)
            stations.append(manifest)
            runs.append({"id": manifest["run_id"], "station_id": manifest["id"], "tick": manifest["tick"], "counts": manifest["counts"]})
        task_records.append({**task, "runs": runs})
    catalog = {
        "schema": "open-task-station-archive-1",
        "tasks": task_records,
        "stations": stations,
        "scope": {
            "included": "Agent dialogue, capsule records, and research-submission evaluations from archived Station runs.",
            "excluded": "Service state, research storage, private execution sessions, provider metadata, internal reasoning, and network configuration.",
        },
    }
    write_json(output / "catalog.json", catalog)
    return catalog


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, action="append", required=True, help="Station runtime data directory; repeat once per run")
    parser.add_argument("--output", type=Path, default=ROOT)
    args = parser.parse_args()
    catalog = export_release(args.source, args.output)
    print(f"Exported {len(catalog['tasks'])} tasks and {len(catalog['stations'])} anonymous runs.")


if __name__ == "__main__":
    main()
