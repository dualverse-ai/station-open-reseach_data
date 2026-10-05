from __future__ import annotations

import gzip
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


if __name__ == "__main__":
    unittest.main()
