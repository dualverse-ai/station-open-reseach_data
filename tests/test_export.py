from __future__ import annotations

import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

try:
    import export_open_tasks as exporter
except ModuleNotFoundError:
    exporter = None


class ExportContractTests(unittest.TestCase):
    def require_exporter(self):
        self.assertIsNotNone(exporter, "runtime archive exporter is missing")
        return exporter

    def test_exporter_module_exists(self):
        self.require_exporter()

    def test_task_detection_uses_research_specification(self):
        module = self.require_exporter()
        cases = {
            "Finding Discrete Emergent Planning Algorithm from a Trained Sokoban Agent": "task-01",
            "Low-Rank Empirical Analysis of Language-Model Logit Tables": "task-02",
            "learned solutions in small k-delay RNNs": "task-03",
            "Mechanisms of Subliminal Learning in Semantically Unrelated Data": "task-04",
            "Distinct Mechanisms of Visual Hallucination in LVLMs": "task-05",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(module.detect_task_id(text), expected)

    def test_dialogue_projection_removes_private_runtime_material(self):
        module = self.require_exporter()
        raw = yaml.safe_dump_all(
            [
                {"tick": 1, "role": "model", "parts": [{"text": "Scientific result."}],
                 "thinking_content": "private reasoning", "thought_signature": "signed",
                 "token_info": {"total": 10}, "api_metadata": {"provider": "sensitive-provider"}},
                {"tick": 2, "role": "model", "parts": [{"text": "Coder Report: session transcript"}]},
                {"tick": 3, "role": "user", "parts": [{"text": "Continue the experiment."}]},
            ],
            sort_keys=False,
        ).encode()

        projected = module.project_dialogue(raw)
        records = list(yaml.safe_load_all(projected.decode()))
        lowered = projected.lower()

        self.assertEqual([record["tick"] for record in records], [1, 3])
        self.assertNotIn(b"thinking_content", lowered)
        self.assertNotIn(b"thought_signature", lowered)
        self.assertNotIn(b"token_info", lowered)
        self.assertNotIn(b"api_metadata", lowered)
        self.assertNotIn(b"coder report", lowered)

    def test_recursive_projection_removes_lines_and_escaped_variants(self):
        module = self.require_exporter()
        value = {
            "content": "Useful result\n/ssd/private/run.py\nFinal stdout should contain a report\nUseful conclusion",
            "nested": ["Keep this", "No web access is available", "storage/system/secret.py", "token_info = private metadata"],
            "thinking_content": "never publish",
        }

        projected = module.sanitize_value(value)
        rendered = yaml.safe_dump(projected, sort_keys=False).lower()

        self.assertIn("useful result", rendered)
        self.assertIn("useful conclusion", rendered)
        for forbidden in ("/ssd/", "final stdout", "web access", "storage/system", "thinking_content", "token_info"):
            self.assertNotIn(forbidden, rendered)

    def test_evaluation_projection_uses_sanitized_coder_report(self):
        module = self.require_exporter()
        source = {
            "instruction": "Measure the effect.",
            "coder": {"backend": "private", "session_id": "secret"},
            "notification": {"message": (
                "Submission completed.\n\n**Coder Report:**\n# Coder Report\n\n"
                "Useful scientific conclusion.\n/ssd/private/run.py\n\n"
                "**Final Stdout:**\nprivate execution log"
            )},
            "final": {"evaluation_details": "Score based on the registered metric.", "primary_score": 2.5},
        }

        public = yaml.safe_load(module.project_evaluation(source).decode())

        self.assertEqual(public, {
            "instruction": "Measure the effect.",
            "coder_report": "Useful scientific conclusion.",
        })

    def test_evaluation_export_normalizes_non_finite_score_to_valid_json(self):
        module = self.require_exporter()
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            source = self.make_source(temp_root / "source", "Emergent Planning")
            output = temp_root / "public"
            (source / "rooms/research/evaluations/1.yaml").write_text(
                "id: 1\ntitle: Evaluation\nauthor: Alpha I\ninstruction: Test\n"
                "final:\n  status: partial\n  primary_score: .nan\n",
                encoding="utf-8",
            )

            module.export_evaluations(source, output)
            raw_index = (output / "evaluations/index.json").read_text(encoding="utf-8")
            index = json.loads(
                raw_index,
                parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
            )

            self.assertNotIn("NaN", raw_index)
            self.assertEqual(index["evaluations"][0]["score"], "n.a.")

    def test_capsule_export_ignores_tools_and_extracts_archive_review_score(self):
        module = self.require_exporter()
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            source = self.make_source(temp_root / "source", "Emergent Planning")
            output = temp_root / "public"
            (source / "capsules/archive/archive_1.yaml").write_text(
                "capsule_id: archive_1\ntitle: Result\nauthor_name: Alpha I\n"
                "messages:\n- author_name: Archive Review System\n  content: |-\n"
                "    **Reviewer Evaluation**\n\n    **Score:** 8.5/10\n",
                encoding="utf-8",
            )
            (source / "capsules/archive/archive_viewer.ipynb").write_text(
                '{"cells": [], "metadata": {}}\n',
                encoding="utf-8",
            )

            records, types = module.export_capsules(source, output)

            self.assertEqual(types, ["archive"])
            self.assertEqual([record["id"] for record in records], ["archive_1"])
            self.assertEqual(records[0]["reviewer_score"], 8.5)

    def test_agent_export_includes_model(self):
        module = self.require_exporter()
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            source = self.make_source(temp_root / "source", "Emergent Planning")
            output = temp_root / "public"

            records = module.export_agents(source, output)
            self.assertEqual(records[0]["model"], "gpt-test")

            (source / "agents/Alpha I.yaml").write_text(
                "agent_name: Alpha I\nstatus: Active\nlineage: Alpha\ngeneration: 1\ntick_birth: 0\n",
                encoding="utf-8",
            )
            records = module.export_agents(source, output)
            self.assertEqual(records[0]["model"], "Unknown")

    def test_release_groups_sources_under_anonymous_task_and_run_ids(self):
        module = self.require_exporter()
        titles = [
            "Finding Discrete Emergent Planning Algorithm from a Trained Sokoban Agent",
            "Low-Rank Empirical Analysis of Language-Model Logit Tables",
            "learned solutions in small k-delay RNNs",
            "Mechanisms of Subliminal Learning in Semantically Unrelated Data",
            "Distinct Mechanisms of Visual Hallucination in LVLMs",
        ]
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            sources = [self.make_source(temp_root / f"private-source-{index}", title) for index, title in enumerate(titles)]
            output = temp_root / "public"

            module.export_release(sources, output)

            catalog = json.loads((output / "catalog.json").read_text())
            self.assertEqual([task["id"] for task in catalog["tasks"]], [f"task-{n:02d}" for n in range(1, 6)])
            self.assertEqual([station["id"] for station in catalog["stations"]], [f"task-{n:02d}/run-01" for n in range(1, 6)])
            self.assertTrue((output / "data/task-01/run-01/agents/index.json").is_file())
            self.assertNotIn("private-source", json.dumps(catalog).lower())
            history_index = json.loads(next((output / "data/task-01/run-01/agents").glob("*/dialogue/index.json")).read_text())
            page = next((output / "data/task-01/run-01/agents").glob("*/dialogue/page-*.yamll.gz"))
            self.assertEqual(gzip.decompress(page.read_bytes()).decode().strip(), "tick: 1\nrole: model\nparts:\n- text: Result")
            self.assertEqual(history_index["format"], "dialogue-yamll-public-1")

    @staticmethod
    def make_source(root: Path, title: str) -> Path:
        (root / "agents/Alpha I").mkdir(parents=True)
        (root / "capsules/archive").mkdir(parents=True)
        (root / "rooms/research/evaluations").mkdir(parents=True)
        (root / "rooms/research/research_task.md").write_text(f"# {title}\n", encoding="utf-8")
        (root / "station_config.yaml").write_text("current_tick: 10\nversion: 1.5.0\n", encoding="utf-8")
        (root / "agents/Alpha I.yaml").write_text(
            "agent_name: Alpha I\nstatus: Active\nlineage: Alpha\ngeneration: 1\ntick_birth: 0\nmodel_name: gpt-test\n",
            encoding="utf-8",
        )
        (root / "agents/Alpha I/llm_chat_history.yamll").write_text(
            "tick: 1\nrole: model\nparts:\n- text: Result\nthinking_content: private\n",
            encoding="utf-8",
        )
        (root / "capsules/archive/archive_1.yaml").write_text(
            "capsule_id: archive_1\ntitle: Result\nauthor_name: Alpha I\ncontent: Evidence\n",
            encoding="utf-8",
        )
        (root / "rooms/research/evaluations/1.yaml").write_text(
            "id: 1\ntitle: Evaluation\nauthor: Alpha I\ninstruction: Test\nfinal:\n  evaluation_details: Pass\n",
            encoding="utf-8",
        )
        return root


if __name__ == "__main__":
    unittest.main()
