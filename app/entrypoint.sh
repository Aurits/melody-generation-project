#!/bin/bash
set -e

echo "Waiting for the database to be available..."
# Increase sleep time if needed (e.g., 20 seconds instead of 10)
sleep 20

echo "Running Alembic migrations..."
alembic upgrade head

echo "Starting the application..."
exec python app.py
