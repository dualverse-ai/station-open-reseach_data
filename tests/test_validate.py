from __future__ import annotations

import gzip
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

try:
    import validate_open_tasks as validator
except ModuleNotFoundError:
    validator = None


class ValidationContractTests(unittest.TestCase):
    def require_validator(self):
        self.assertIsNotNone(validator, "strict runtime archive validator is missing")
        return validator

    def test_validator_module_exists(self):
        self.require_validator()

    def test_scanner_rejects_release_branding_and_source_identifiers(self):
        module = self.require_validator()
        samples = [
            "Station " + "V" + "2",
            "station_data_" + "v" + "2",
            "submitted_public_" + "v" + "2",
            "epstation-0610_v15beta",
            "slstation-0814",
            "zr_station2",
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertTrue(module.scan_bytes(sample.encode(), Path("sample.txt")))

    def test_scanner_rejects_private_terms_after_unescaping(self):
        module = self.require_validator()
        samples = [
            rb"useful\nCoder Report: hidden",
            rb"useful\n/ssd/private/file",
            rb"useful\nstorage/system/run.py",
            rb"model: codex",
            rb"thinking_content: hidden",
            rb"https://api.example.test/v1/responses",
            rb"No web access is available",
            rb"coder_sessions/session/transcript.jsonl",
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertTrue(module.scan_bytes(sample, Path("record.yaml.gz")))

    def test_scanner_allows_public_coder_report_heading(self):
        module = self.require_validator()
        value = b"coder_report: Scientific findings only."
        path = Path("data/task-01/run-01/evaluations/records/1.yaml.gz")
        self.assertEqual(module.scan_bytes(value, path), [])

        viewer = b"item.coder_report; label = 'Coder Report'"
        self.assertEqual(module.scan_bytes(viewer, Path("assets/app.js")), [])

    def test_scanner_accepts_scientific_model_discussion(self):
        module = self.require_validator()
        value = b"A language model and a vision-language model were evaluated offline."
        self.assertEqual(module.scan_bytes(value, Path("record.yaml.gz")), [])

    def test_public_files_scan_inside_gzip_payloads(self):
        module = self.require_validator()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "record.yaml.gz"
            path.write_bytes(gzip.compress(b"content: Coder Report should be private\n", mtime=0))

            findings = module.scan_public_files(root)

        self.assertTrue(any("coder" in finding.lower() for finding in findings))

    def test_release_scanner_allows_only_documented_public_urls_in_readme(self):
        module = self.require_validator()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            readme = root / "README.md"
            readme.write_text(
                "https://arxiv.org/abs/2610.08927\n"
                "https://dualverse-ai.github.io/station-open-reseach_data/\n"
                "https://github.com/dualverse-ai/station-open-reseach\n",
                encoding="utf-8",
            )
            self.assertEqual(module.scan_public_files(root), [])

            for value in (
                "https://private.example.test/data\n",
                "https://github.com/dualverse-ai/station-open-reseach.evil.example\n",
            ):
                with self.subTest(value=value):
                    readme.write_text(value, encoding="utf-8")
                    self.assertTrue(module.scan_public_files(root))

    def test_report_index_validation_checks_integrity_and_privacy(self):
        module = self.require_validator()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            station_root = root / "data/task-01/run-01"
            payload_path = station_root / "reports/records/report-01.md.gz"
            payload_path.parent.mkdir(parents=True)
            raw = b"# Public report\n\nEvidence.\n"
            payload_path.write_bytes(gzip.compress(raw, mtime=0))
            record = {
                "id": "report-01",
                "key": "report-01",
                "title": "Public report",
                "file": "reports/records/report-01.md.gz",
                "bytes": len(raw),
                "compressed_bytes": payload_path.stat().st_size,
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
            index_path = station_root / "reports/index.json"
            index_path.parent.mkdir(parents=True, exist_ok=True)
            index_path.write_text(json.dumps({"schema": "station-research-reports-1", "reports": [record]}), encoding="utf-8")
            expected_paths = set()

            errors = module.validate_report_index(index_path, station_root, root, 1, expected_paths)
            self.assertEqual(errors, [])
            self.assertEqual(expected_paths, {index_path, payload_path})

            record["sha256"] = "0" * 64
            index_path.write_text(json.dumps({"schema": "station-research-reports-1", "reports": [record]}), encoding="utf-8")
            errors = module.validate_report_index(index_path, station_root, root, 1, set())
            self.assertTrue(any("integrity mismatch" in error for error in errors))

            private_raw = b"# Private\n\n/ssd/private/result.txt\n"
            payload_path.write_bytes(gzip.compress(private_raw, mtime=0))
            record["bytes"] = len(private_raw)
            record["sha256"] = hashlib.sha256(private_raw).hexdigest()
            index_path.write_text(json.dumps({"schema": "station-research-reports-1", "reports": [record]}), encoding="utf-8")
            errors = module.validate_report_index(index_path, station_root, root, 1, set())
            self.assertTrue(any("internal path" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
