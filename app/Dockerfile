FROM python:3.11-slim

WORKDIR /app

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
