# Setup on Google Cloud VM

> **Target image**: fresh Debian / Ubuntu VM with GPU attached (e.g. A100). Only Docker + driver pre‑installed.

## 1. Provision VM
```bash
# Example: n1-standard-8 + NVIDIA T4
gcloud compute instances create melody-gpu \
  --zone=us-central1-a \
  --machine-type=n1-standard-8 \
  --accelerator=type=nvidia-tesla-t4,count=1 \
  --maintenance-policy=TERMINATE \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=100GB \
  --tags=http-server,https-server
```

## 2. Install prerequisites
```bash
# GPU driver (CUDA 12)
sudo apt-get update && sudo apt-get install -y nvidia-driver-535
# Docker + Compose
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker
```

## 3. Clone repo & pull submodules
```bash
git clone --recursive https://github.com/Aurits/melody-generation-project.git
cd melody-generation-project
```

## 4. Drop model files
```
# GETMusic checkpoint
mkdir -p tmik_bgm_conditional_melody_generation/checkpoints
scp checkpoint.pth melody-gpu:~/melody-generation-project/tmik_bgm_conditional_melody_generation/checkpoints/
# Dreamtonics SDK (unzipped folder)
scp -r dreamtonics_sdk melody-gpu:~/melody-generation-project/tmik_make_vocal_mix/
```

## 5. Build & start
```bash
# Build all images (first run ≈ 15 min)
docker compose build
# Launch in background
docker compose up -d
```

## 6. Verify
| Step | Command | Expected |
|------|---------|----------|
| Containers | `docker ps` | 4 services UP |
| Health | `curl http://localhost` | Gradio landing page |
| DB | `docker exec -it postgres-database psql -U postgres -c "\dt"` | `jobs` table |

## 7. Expose or secure
* Map `80` → load‑balancer or set up Cloud Armor.
* For private use, restrict firewall and require VPN.

