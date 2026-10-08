from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ViewerContractTests(unittest.TestCase):
    def test_viewer_is_local_grouped_and_neutral(self):
        index = (ROOT / "index.html").read_text(encoding="utf-8") if (ROOT / "index.html").is_file() else ""
        app = (ROOT / "assets/app.js").read_text(encoding="utf-8") if (ROOT / "assets/app.js").is_file() else ""
        combined = (index + "\n" + app).lower()

        self.assertIn("open task station archive", combined)
        self.assertIn("catalog.tasks", app)
        self.assertIn("task.runs", app)
        self.assertNotIn("raw.githubusercontent.com", combined)
        self.assertNotIn("github.com", combined)
        self.assertNotIn("station " + "v" + "2", combined)
        self.assertNotIn("station_data_" + "v" + "2", combined)

    def test_viewer_has_no_notebook_or_artifact_routes(self):
        app_path = ROOT / "assets/app.js"
        self.assertTrue(app_path.is_file(), "viewer application is missing")
        app = app_path.read_text(encoding="utf-8")
        self.assertNotIn("#/notebooks", app)
        self.assertNotIn("catalog.artifacts", app)
        self.assertNotIn("thinking_content", app)
        self.assertNotIn("thinking_text", app)

    def test_question_tab_is_not_in_navigation(self):
        index = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('data-page="question"', index)

    def test_viewer_has_research_report_routes(self):
        index = (ROOT / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "assets/app.js").read_text(encoding="utf-8")

        self.assertIn('data-page="reports"', index)
        self.assertIn("reports/index.json", app)
        self.assertIn("renderReports", app)
        self.assertIn("renderReport", app)
        self.assertIn("page === 'reports'", app)
        self.assertIn("page === 'report'", app)


if __name__ == "__main__":
    unittest.main()
