#!/bin/bash
set -e

echo "Waiting for the database to be available..."
# Increase sleep time if needed (e.g., 10 seconds)
sleep 10

echo "Running Alembic migrations..."
alembic upgrade head

echo "Starting the application..."
exec python app.py
