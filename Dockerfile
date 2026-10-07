FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies first (for optimal Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code and data assets
COPY . .

# Remove any lingering lock file from repository
RUN rm -f data/qdrant_db/.lock

# Expose default HTTP port
EXPOSE 8000

# Start FastAPI application using dynamic port entrypoint
CMD ["python", "start.py"]
