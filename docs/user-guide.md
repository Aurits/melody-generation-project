# User Guide – Melody → Vocal Mix

## 1. Quick start
1. Open **http://SERVER_IP** in your browser.
2. Click **Upload Backing Track** → choose a `.wav` file.
3. *(Optional)* Expand **Advanced Settings** to tweak BPM, start‑time or seed.
4. Hit **Generate Melodies**. Status appears top‑right.

## 2. Understanding outputs
| Widget | File | Purpose |
|--------|------|---------|
| Vocal Track | `vocal_melody_*.wav` | Synth‑only vocal line |
| Mixed Track | `mixed_audio_*.wav` | Backing + vocal mix |
| Beat Mix | `beat_mix_*.wav` | Debug: beat‑aligned mix |
| MIDI Melody | `melody_*.mid` | Raw melody for further edit |

All artefacts download‑ready and also stored in **`shared_data/vocal_results/`**.

## 3. Job table
* **✅ completed** – click _Show/Hide Files_ to browse signed GCS links.
* **⏳ processing** – still running (refresh).
* **❌ failed** – hover row for tooltip, check `integrated-app` logs.

## 4. Tips & tricks
* **Randomize seed** for creative diversity.
* Provide *both* `start_time` & `bpm` if the default beat‑estimator struggles.
* Long songs ➜ current model outputs first ~32 bars. Stitch multiple segments or wait for forthcoming “batch generation” support.

## 5. CLI / API (advanced)
POST to `/upload` with multipart file → returns `job_id`.
GET `/jobs/{id}` → JSON status and GCS URLs.
(See `docs/api.md` if enabled.)

## 6. Troubleshooting
| Symptom | Fix |
|---------|-----|
| Job stuck **processing** | Check GPU utilisation: `docker stats melody-generation` |
| No output files | Ensure checkpoint & SDK volumes present |
| 502 Gateway | Integrated‑app container crashed → `docker logs integrated-app` |

## 7. House‑keeping
* Download results within **7 days** (expiry of signed URLs).
* Clean `shared_data/*` if disk fills up.

