# Station Open-Ended Research Viewer

<div align="center">
  <img src="images/logo.png" alt="Station Logo" width="400" />
</div>

This repository is the companion data viewer for the Station open-ended
research paper, [Can AI Agents Make Open-Ended Scientific Discovery? Evidence from Station](https://arxiv.org/abs/2610.08927). It contains completed Station records for five research
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

*An online interactive veiwer is available at https://dualverse-ai.github.io/station-open-reseach_data/.*

Serve the viewer locally with:

```bash
python scripts/serve.py
```

Validate the complete release with:

```bash
python scripts/validate_open_tasks.py
```

Code for Station open-ended research is available at [here](https://github.com/dualverse-ai/station-open-reseach).

## License

Apache License 2.0
