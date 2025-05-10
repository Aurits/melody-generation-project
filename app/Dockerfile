# Dockerfile for the Melody Generation Project Integrated app
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including Git, build tools, fluidsynth, and unzip
RUN apt-get update && apt-get install -y \
    git \
    libomp5 \
    unzip \
    build-essential \
    python3-dev \
    libsndfile1-dev \
    fluidsynth \
    libfluidsynth-dev \
    && rm -rf /var/lib/apt/lists/*


# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app code including the Alembic config and entrypoint script
COPY . .

# Make entrypoint script executable
RUN chmod +x entrypoint.sh

EXPOSE 7860

# Use the entrypoint script to run migrations and start the app
ENTRYPOINT ["./entrypoint.sh"]