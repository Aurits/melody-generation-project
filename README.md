# AI Melody & Vocal Generation Project

This repository provides an end-to-end platform for generating AI-driven melodies from background tracks, then combining them with synthesized vocals for a complete musical composition. The project unifies separate model repositories – **tmik_bgm_conditional_melody_generation** for melody generation (GETMusic-based) and **tmik_make_vocal_mix** for vocal mixing (Dreamtonics-based) – under one “mother” repository, with clear steps for setup, usage, and management.

---

## Table of Contents

1. [Overview](#overview)  
2. [Repository Structure](#repository-structure)  
3. [Key Components](#key-components)  
4. [Setup on Google Cloud VM](#setup-on-google-cloud-vm)  
5. [Running the Project](#running-the-project)  
6. [Usage Workflow](#usage-workflow)  
7. [Database & Persistence](#database--persistence)  
8. [Managing Models & Large Files](#managing-models--large-files)  
9. [Project Maintenance](#project-maintenance)  
10. [Contributing](#contributing)  
11. [License](#license)

---

## 1. Overview

- **Melody Generation:** Uses GETMusic to analyze a background track (WAV/MP3/MID) and produce a `.mid` file representing the new melody. By default, the model generates ~32 bars, so if your track is longer, the final output is truncated.
- **Vocal Mixing:** Takes the generated melody and the original background track, synthesizes vocal lines, and produces a final `.wav` mix. Additional user inputs (like lyrics or “all_la” singing) can be incorporated via command-line flags.
- **Integrated Application:** Provides a user interface (Gradio) for uploading, job submission, status tracking, and downloading results. Persists job data in PostgreSQL.

---

## 2. Repository Structure

```
project-root/
├── docker-compose.yml                # Orchestrates the entire system
├── .env                              # Environment variables for DB, etc.
├── shared_data/                      # Shared volume for file exchange
│   ├── input/                        # User-uploaded background tracks
│   ├── melody_results/               # Generated MIDI files
│   └── vocal_results/                # Final mixed compositions
├── app/                              # Integrated application code
│   ├── app.py                        # Gradio UI and main application
│   ├── job_manager.py                # Background worker managing job queue
│   ├── models.py                     # SQLAlchemy models (Job, etc.)
│   ├── service.py                    # Docker-based calls to model services
│   ├── requirements.txt              # Python dependencies
│   ├── database.py                   # DB session logic (optional)
│   └── alembic/                      # DB migration scripts if needed
├── tmik_bgm_conditional_melody_generation/  # Melody generation submodule
│   ├── Dockerfile
│   ├── melody_generation.py
│   └── ...
└── tmik_make_vocal_mix/              # Vocal mixing submodule
    ├── Dockerfile
    ├── make_vocalmix.py
    └── ...
```

- **docker-compose.yml**: Declares how containers (Postgres, the integrated app, the model services) interact.  
- **tmik_bgm_conditional_melody_generation & tmik_make_vocal_mix**: Remain separate modules for the two models.

---

## 3. Key Components

1. **PostgreSQL Database**  
   Stores job records, input file paths, job statuses, and final outputs.  
2. **Melody Generation Model**  
   A Docker container running GETMusic-based code. By default, it generates ~32 bars of melody.  
3. **Vocal Mixing Model**  
   A Docker container using Dreamtonics or similar SDK to synthesize vocals from the `.mid` file.  
4. **Gradio Application**  
   The main user-facing component. Upload tracks, create jobs, track progress, retrieve final `.wav` and `.mid` files.

---

## 4. Setup on Google Cloud VM

1. **Install Docker & NVIDIA Drivers**  
   - [Install Docker Engine](https://docs.docker.com/engine/install/)  
   - [Install NVIDIA GPU drivers](https://docs.nvidia.com/datacenter/tesla/tesla-installation-notes/) (if using GPU acceleration).
2. **Clone the Repository**  
   ```bash
   git clone https://github.com/YourOrg/melody-generation-project.git
   cd melody-generation-project
   ```
3. **Set Environment Variables**  
   - Copy `.env.example` to `.env`.
   - Edit for DB credentials, custom ports, etc.
4. **Add Model Checkpoints**  
   - Place GETMusic checkpoint in `tmik_bgm_conditional_melody_generation/checkpoints/`.
   - Place Dreamtonics SDK in `tmik_make_vocal_mix/dreamtonics_sdk/` (if required).

---

## 5. Running the Project

1. **Build & Start Containers**  
   ```bash
   docker compose build
   docker compose up -d
   ```
2. **Check Logs**  
   ```bash
   docker compose logs -f integrated_app
   ```
   to ensure the Gradio app starts successfully.

3. **Access the App**  
   By default, the integrated app listens on `http://<vm-public-ip>:80`.

---

## 6. Usage Workflow

1. **Upload a Background Track**  
   - Through the Gradio UI or an API endpoint (if you have one), place your `.wav` or `.mp3` file in `/shared_data/input/`.
2. **Create a Job**  
   - The app stores a record in Postgres with status = “pending”.
3. **Melody Generation**  
   - The job manager triggers `tmik_bgm_conditional_melody_generation` container, which produces `melody.mid` in `/shared_data/melody_results/`.
4. **Vocal Mixing**  
   - After melody generation, the job manager calls the mixing container (tmik_make_vocal_mix) with the original BGM + `.mid` file, generating a final `mix.wav`.
5. **Track Status & Download**  
   - The job status changes to “completed” once the final mix is done. Users can download files from `/shared_data/vocal_results/` or the UI.

---

## 7. Database & Persistence

- **Database**  
  - Default: PostgreSQL (in Docker container).  
  - Example usage: job statuses, input file references, final output paths.  
- **Redis** (Optional)  
  - If you choose to incorporate a queueing mechanism, you might use Redis. Document the reason if you do (caching vs. persistent store).  
- **Backup & Restore**  
  - Postgres: `pg_dump` / `pg_restore`.  
  - Redis (if used): BGSAVE or RDB/AOF files.

---

## 8. Managing Models & Large Files

- **Submodules**  
  If `tmik_bgm_conditional_melody_generation` and `tmik_make_vocal_mix` are submodules, update them independently as needed.
- **.gitignore**  
  Large model checkpoints or Dreamtonics SDK can be excluded from Git commits, storing them on local disk or external storage.
- **Mounting Directories**  
  For bigger model files, mount volumes at runtime (`docker run -v /host/path:/app/checkpoints`) to avoid rebuilding images.

---

## 9. Project Maintenance

- **README Updates**:  
  Keep environment setup, usage instructions, and known issues updated.  
- **API Documentation**:  
  If exposing a REST API beyond Gradio, use a doc generator (Swagger or FastAPI docs) with explicit error handling (e.g., 415 for invalid file type, 500 for server errors).
- **Version Control**:  
  - Master/Production branches for stable releases.  
  - Dev/feature branches for experimental changes.  
- **Logging & Monitoring**:  
  Consider centralizing container logs or adding an aggregator (like ELK stack) if usage scales.

---

## 10. Contributing

1. **Fork** the repo and create feature branches.  
2. **Pull Requests** should include a clear summary, relevant tests, and updated docs when changing behavior.  
3. **Code Reviews** ensure consistent architecture and style.

---

## 11. License

- This project uses third-party AI libraries and may contain code under special research or commercial licenses (GETMusic, Dreamtonics).  
- Ensure you have permission to use these models in your environment.

---

### Final Note

For additional support or feedback, open issues or discussion threads in the repository. The dev environment is available at:
- **App Demo**: [http://34.55.17.253/](http://34.55.17.253/)  
- **Repo**: [https://github.com/Aurits/melody-generation-project](https://github.com/Aurits/melody-generation-project)

We appreciate your contributions and help in making AI-based music creation more accessible!