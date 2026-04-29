# Python version pinned to 3.11 — ensure local dev matches (see pyproject.toml)
FROM python:3.11-slim AS builder

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies in a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install -r requirements.txt

# Final stage
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Create unprivileged user
RUN useradd -m euroscope

# Set up data directory with correct permissions
RUN mkdir -p /app/data && chown euroscope:euroscope /app/data

# Copy project source code
COPY --chown=euroscope:euroscope . /app/

# Switch to standard user
USER euroscope

# Expose API/Mini App port
EXPOSE 8080

# Run EuroScope
CMD ["python", "main.py"]
