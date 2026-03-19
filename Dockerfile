# sage/Dockerfile
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

# Copy ONLY dependency files first — cached unless pyproject.toml changes
COPY pyproject.toml ./

# Install dependencies into venv — this layer is cached
RUN uv venv && uv pip install --no-cache \
    fastapi uvicorn asyncpg httpx \
    pydantic-settings cryptography \
    supabase python-jose python-dotenv \
    google-cloud-documentai

# NOW copy app code — changes here don't invalidate dep cache
COPY ./sage ./sage
COPY ./static ./static

EXPOSE 8000

CMD ["uvicorn", "sage.main:app", "--host", "0.0.0.0", "--port", "8000"]