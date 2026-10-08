from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

try:
    import backfill_agent_models as backfill
except ModuleNotFoundError:
    backfill = None


class AgentModelBackfillTests(unittest.TestCase):
    def test_backfill_script_does_not_publish_private_source_mapping(self):
        script = (ROOT / "scripts/backfill_agent_models.py").read_text(encoding="utf-8")
        for source_prefix in ("epstation-", "lrststion-", "rnststion-", "seed1new"):
            self.assertNotIn(source_prefix, script)

    def test_backfills_known_models_and_marks_unavailable_models_unknown(self):
        self.assertIsNotNone(backfill, "Agent model backfill is missing")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            release_root = root / "release"
            source_root = root / "source"
            known_index = release_root / "data/task-01/run-01/agents/index.json"
            unknown_index = release_root / "data/task-04/run-01/agents/index.json"
            known_index.parent.mkdir(parents=True)
            unknown_index.parent.mkdir(parents=True)
            known_index.write_text(json.dumps({"agents": [{"name": "Alpha I"}]}), encoding="utf-8")
            unknown_index.write_text(json.dumps({"agents": [{"name": "Beta I"}]}), encoding="utf-8")
            metadata = source_root / "known/agents/Alpha I.yaml"
            metadata.parent.mkdir(parents=True)
            metadata.write_text("agent_name: Alpha I\nmodel_name: gpt-test\n", encoding="utf-8")

            result = backfill.backfill_models(
                source_root,
                release_root,
                {"task-01/run-01": Path("known")},
            )

            known = json.loads(known_index.read_text())["agents"][0]
            unknown = json.loads(unknown_index.read_text())["agents"][0]
            self.assertEqual(known["model"], "gpt-test")
            self.assertEqual(unknown["model"], "Unknown")
            self.assertEqual(result, {"stations": 2, "agents": 2, "resolved": 1})


if __name__ == "__main__":
    unittest.main()
