# System Architecture

## High‑level diagram
```
User ─▶ Integrated‑App (Gradio + Worker)
           ├──▶ Melody‑Service  (GETMusic)
           ├──▶ Vocal‑Service   (Dreamtonics)
           └──▶ PostgreSQL  ──┐
                             ▼
                         Shared‑Volume (/shared_data)
```

| Layer | Responsibility | Technology |
|-------|----------------|------------|
| **UI / API** | Upload, job creation, status polling | Gradio (FastAPI under the hood) |
| **Job Manager** | Async queue, passes CLI flags to each container | Python threads (no Redis) |
| **Model Services** | Heavy GPU inference | Docker, PyTorch / Dreamtonics‑SDK |
| **Persistence** | Job metadata & GCS URLs | PostgreSQL 10‑alpine |
| **File Bus** | Large artefacts exchanged between services | bind‑mounted `shared_data/` |

### Data flow
1. **Upload** ⇒ file written to `shared_data/input/` and a *pending* job row is added.
2. Worker spawns melody container → writes `melody_results/`.
3. Worker spawns vocal container → writes `vocal_results/`.
4. On success it uploads artefacts to GCS and updates the job row with public URLs.

### Scaling notes
* Containers keep their model checkpoints in RAM (one process per service) ⇒ fast, GPU‑friendly.
* Horizontal scaling = run more `integrated_app` nodes behind a LB; `shared_data` can be NFS or GCS‑Fuse.

