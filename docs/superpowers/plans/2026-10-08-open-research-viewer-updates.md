# Open Research Viewer Updates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore Agent model metadata, remove the unused Question navigation entry, and publish three final research reports for each tick-300 Station run.

**Architecture:** Keep the existing anonymous static archive schema and add a `reports` index plus deterministic gzip Markdown payloads under each run. A dedicated importer maps the nine evaluation groups to anonymous run IDs, updates catalog counts, and never emits source paths; the existing validator gains referential, integrity, count, and privacy checks for the new records. The Viewer adds list/detail routes and hides the Reports entry on runs without reports.

**Tech Stack:** Python 3, PyYAML, static HTML/CSS/JavaScript, deterministic gzip, `unittest`.

---

### Task 1: Restore model metadata

**Files:**
- Modify: `tests/test_export.py`
- Modify: `scripts/export_open_tasks.py`
- Create: `scripts/backfill_agent_models.py`
- Modify: `data/task-*/run-*/agents/index.json`

- [ ] **Step 1: Write the failing exporter test**

Add `model_name: gpt-test` to the synthetic Agent metadata and assert the exported Agent record contains `"model": "gpt-test"`. Add a second assertion that missing metadata exports `"model": "Unknown"`.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python3 -m unittest tests.test_export.ExportContractTests.test_agent_export_includes_model -v`

Expected: FAIL because `export_agents()` currently omits `model`.

- [ ] **Step 3: Add the minimal projection**

Add this field to the Agent record:

```python
"model": safe_metadata.get("model_name") or "Unknown",
```

Implement `backfill_agent_models.py` so existing public indexes are updated from the corresponding private snapshots by Agent name, while runs whose source metadata is unavailable receive `Unknown`. Do not emit source paths or source IDs into public JSON.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `python3 -m unittest tests.test_export.ExportContractTests.test_agent_export_includes_model -v`

Expected: PASS.

### Task 2: Remove the Question navigation entry

**Files:**
- Modify: `tests/test_viewer.py`
- Modify: `index.html`

- [ ] **Step 1: Write the failing Viewer contract test**

Read `index.html` and assert it does not contain `data-page="question"`.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python3 -m unittest tests.test_viewer.ViewerContractTests.test_question_tab_is_not_in_navigation -v`

Expected: FAIL because the navigation still exposes Questions.

- [ ] **Step 3: Remove only the navigation anchor**

Delete the `<a data-page="question">Questions</a>` entry. Keep existing Question data and deep-link routing intact so archived links remain valid.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run the same focused command and expect PASS.

### Task 3: Import tick-300 research reports

**Files:**
- Create: `scripts/import_research_reports.py`
- Create: `tests/test_reports.py`
- Generate: `data/task-01/run-01/reports/` through `data/task-03/run-03/reports/`
- Generate: empty report indexes for `data/task-04/run-01/` and `data/task-05/run-01/`
- Modify: `catalog.json`
- Modify: `data/task-*/run-*/manifest.json`

- [ ] **Step 1: Write failing importer tests**

Construct a temporary release with one anonymous run and a temporary evaluation group containing three `direct_*` directories. Assert the importer creates exactly three deterministic gzip Markdown records, extracts each first-level heading as the title, updates both catalog and manifest counts, and raises `ValueError` when a mapped group does not contain exactly three reports.

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m unittest tests.test_reports -v`

Expected: import failure because `import_research_reports` does not exist.

- [ ] **Step 3: Implement the minimal importer**

Expose `import_reports(source_root: Path, release_root: Path = ROOT, source_map: dict[str, Path] | None = None) -> dict[str, int]`, returning the imported station and report totals. Require mappings to be passed explicitly at runtime so private source IDs are not stored in the public repository.

For each mapped run, sort its three `direct_*` directories, sanitize `draft/research_paper.md`, write `reports/records/report-01.md.gz` through `report-03.md.gz`, and write `reports/index.json` with `id`, `key`, `title`, `file`, `bytes`, `compressed_bytes`, and `sha256`. Create empty indexes for unmapped runs and update `counts.reports` in catalog task runs, catalog stations, and run manifests.

- [ ] **Step 4: Run tests and verify GREEN**

Run the same focused command and expect all tests to pass.

- [ ] **Step 5: Generate public report data**

Run: `python3 scripts/import_research_reports.py "$REPORT_ROOT"`

Expected: 27 reports imported across nine tick-300 runs; two later-tick runs receive empty indexes.

### Task 4: Add Research Reports Viewer routes

**Files:**
- Modify: `tests/test_viewer.py`
- Modify: `index.html`
- Modify: `assets/app.js`

- [ ] **Step 1: Write failing Viewer route tests**

Assert the static Viewer contains a `data-page="reports"` navigation entry, fetches `reports/index.json`, defines list and detail renderers, and routes `reports` plus `report/<key>`.

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m unittest tests.test_viewer -v`

Expected: FAIL because no report routes exist.

- [ ] **Step 3: Implement list and detail views**

Add a Reports navigation anchor. Render a compact title/ID table for the list and render decompressed Markdown in the existing `record-paper` layout for details. In `showNavbar()`, hide the Reports anchor when `station.counts.reports` is zero; map detail routes back to the Reports active tab.

- [ ] **Step 4: Run tests and verify GREEN**

Run the same focused command and expect PASS.

### Task 5: Validate reports and the complete release

**Files:**
- Modify: `tests/test_validate.py`
- Modify: `scripts/validate_open_tasks.py`
- Modify: `scripts/build_pages.py`
- Modify: `README.md`

- [ ] **Step 1: Write failing report validation tests**

Add a temporary report index and payload test that proves the validator rejects wrong SHA-256, unsafe relative paths, count mismatches, missing files, unreferenced report payloads, and forbidden source/private content after decompression.

- [ ] **Step 2: Run focused validation tests and verify RED**

Run: `python3 -m unittest tests.test_validate -v`

Expected: the report-specific contract fails because reports are not traversed.

- [ ] **Step 3: Extend strict validation**

Require one report index per run, exactly three reports for tick-300 tasks and zero for later-tick tasks, safe unique keys, gzip readability, byte length and SHA-256 integrity, decoded privacy scanning, and exact file closure. Keep `data` in the static build and document the new report records in README.

- [ ] **Step 4: Run complete verification**

Run:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_open_tasks.py
python3 scripts/build_pages.py
```

Expected: all unit tests pass, strict validation reports `status: pass`, and `_site` contains all report indexes and payloads.

- [ ] **Step 5: Perform browser smoke checks**

Serve the archive locally and verify a representative Agent shows its model, Questions is absent from the navigation, a tick-300 run lists three reports, a report renders Markdown, and later-tick runs do not show the Reports tab.
