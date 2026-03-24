# sage/Dockerfile
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"
ENV PORT=5463
ENV HOST=0.0.0.0

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

# Copy all metadata and code
COPY pyproject.toml uv.lock ./
COPY ./sage ./sage
COPY ./static ./static

# Install dependencies strictly from lockfile
RUN uv sync --no-dev --no-cache

EXPOSE $PORT

# Run in production mode
CMD ["uvicorn", "sage.main:app", "--host", $HOST, "--port", $PORT, "--proxy-headers"]