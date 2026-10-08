from __future__ import annotations

import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

try:
    import import_research_reports as importer
except ModuleNotFoundError:
    importer = None


class ResearchReportImportTests(unittest.TestCase):
    def require_importer(self):
        self.assertIsNotNone(importer, "research report importer is missing")
        return importer

    def test_importer_does_not_publish_private_source_mapping(self):
        script = (ROOT / "scripts/import_research_reports.py").read_text(encoding="utf-8")
        for source_prefix in ("epstation-", "lrststion-", "rnststion-"):
            self.assertNotIn(source_prefix, script)

    def test_imports_three_deterministic_reports_and_updates_counts(self):
        module = self.require_importer()
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            source_root = temp_root / "source"
            release_root = temp_root / "release"
            self.make_release(release_root)
            self.make_reports(source_root / "group", 3)

            result = module.import_reports(
                source_root,
                release_root,
                {"task-01/run-01": Path("group")},
            )
            first_payloads = sorted((release_root / "data/task-01/run-01/reports/records").glob("*.gz"))
            first_bytes = [path.read_bytes() for path in first_payloads]

            self.assertEqual(result, {"stations": 1, "reports": 3})
            self.assertEqual(len(first_payloads), 3)
            index = json.loads((release_root / "data/task-01/run-01/reports/index.json").read_text())
            self.assertEqual([item["title"] for item in index["reports"]], ["Report 1", "Report 2", "Report 3"])
            self.assertEqual(gzip.decompress(first_payloads[0].read_bytes()).decode(), "# Report 1\n\nEvidence 1\n")

            module.import_reports(source_root, release_root, {"task-01/run-01": Path("group")})
            second_payloads = sorted((release_root / "data/task-01/run-01/reports/records").glob("*.gz"))
            self.assertEqual([path.read_bytes() for path in second_payloads], first_bytes)

            catalog = json.loads((release_root / "catalog.json").read_text())
            manifest = json.loads((release_root / "data/task-01/run-01/manifest.json").read_text())
            self.assertEqual(catalog["stations"][0]["counts"]["reports"], 3)
            self.assertEqual(catalog["tasks"][0]["runs"][0]["counts"]["reports"], 3)
            self.assertEqual(manifest, catalog["stations"][0])

    def test_requires_exactly_three_reports_per_mapped_station(self):
        module = self.require_importer()
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            self.make_release(temp_root / "release")
            self.make_reports(temp_root / "source/group", 2)

            with self.assertRaisesRegex(ValueError, "exactly 3"):
                module.import_reports(
                    temp_root / "source",
                    temp_root / "release",
                    {"task-01/run-01": Path("group")},
                )

    def test_mapping_parser_rejects_absolute_and_parent_paths(self):
        module = self.require_importer()
        self.assertEqual(
            module.parse_source_map(["task-01/run-01=group-a"]),
            {"task-01/run-01": Path("group-a")},
        )
        for value in ("missing-separator", "task-01/run-01=/private", "task-01/run-01=../private"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                module.parse_source_map([value])

    @staticmethod
    def make_release(root: Path) -> None:
        station = {
            "id": "task-01/run-01",
            "task_id": "task-01",
            "run_id": "run-01",
            "title": "Example - Run 1",
            "tick": 301,
            "status": "Archived",
            "counts": {"agents": 0, "capsules": 0, "evaluations": 0},
            "capsule_types": [],
        }
        catalog = {
            "schema": "open-task-station-archive-1",
            "tasks": [{
                "id": "task-01",
                "title": "Example",
                "description": "Example task",
                "runs": [{
                    "id": "run-01",
                    "station_id": "task-01/run-01",
                    "tick": 301,
                    "counts": dict(station["counts"]),
                }],
            }],
            "stations": [station],
        }
        station_root = root / "data/task-01/run-01"
        station_root.mkdir(parents=True)
        (root / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
        (station_root / "manifest.json").write_text(json.dumps(station), encoding="utf-8")

    @staticmethod
    def make_reports(root: Path, count: int) -> None:
        for number in range(1, count + 1):
            draft = root / f"direct_{number:02d}" / "draft"
            draft.mkdir(parents=True)
            (draft / "research_paper.md").write_text(
                f"# Report {number}\n\nEvidence {number}\n",
                encoding="utf-8",
            )


if __name__ == "__main__":
    unittest.main()
