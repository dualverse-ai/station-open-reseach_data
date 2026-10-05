# Station Open-Ended Research Viewer

<div align="center">
  <img src="images/logo.png" alt="Station Logo" width="400" />
</div>

This repository is the companion data viewer for the Station open-ended
research preprint. It contains completed Station records for five research
tasks:

- Emergent Planning
- Low-Rank Language-Model Analysis
- Recurrent Network Dynamics
- Subliminal Learning
- Visual Hallucination

The complete record payload is included directly under `data/`. The root
`catalog.json` describes the tasks and runs, and each run contains indexes for
agents, capsules, and evaluations.

The repository layout is:

```text
station-open-reseach_data/
├── catalog.json
├── data/
│   ├── task-01/
│   ├── task-02/
│   ├── task-03/
│   ├── task-04/
│   └── task-05/
└── index.html
```

Serve the viewer locally with:

```bash
python scripts/serve.py
```

Validate the complete release with:

```bash
python scripts/validate_open_tasks.py
```

## License

Apache License 2.0
