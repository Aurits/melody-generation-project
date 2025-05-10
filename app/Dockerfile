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

# Set environment variables for numpy to ensure compatibility with madmom
ENV OPENBLAS_NUM_THREADS=1
ENV MKL_NUM_THREADS=1
ENV NUMEXPR_NUM_THREADS=1
ENV OMP_NUM_THREADS=1

# Install specific numpy version before other requirements to resolve madmom dependency issue
RUN pip install --no-cache-dir numpy==1.23.5 cython==0.29.36

# Install older scipy version for compatibility with madmom
RUN pip install --no-cache-dir scipy==1.10.1

# Install madmom separately before other requirements
RUN pip install --no-cache-dir git+https://github.com/CPJKU/madmom.git

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