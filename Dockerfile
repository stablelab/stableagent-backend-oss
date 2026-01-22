# Use Python 3.13 base image
FROM python:3.13-slim

# Install system dependencies needed by psycopg2 and uv
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv sync --frozen --no-dev

# Copy application code
COPY src/ ./src/

# Expose default port for local run (Cloud Run uses env PORT)
EXPOSE 8080

# Cloud Run provides the PORT env; default to 8080 for local/dev
ENV PORT=8080 \
    PYTHONUNBUFFERED=1

# Start the server using the dynamic PORT
# Start Uvicorn with the FastAPI app entrypoint
CMD ["/bin/sh", "-c", "uv run uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8080}"]