FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Install system dependencies if required
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv globally
RUN pip install uv

COPY pyproject.toml ./ 
# (If pyproject.toml doesn't exist directly or user uses standard uv init structure)
COPY ./sage ./sage
COPY ./static ./static

# Instead of pip installing, leveraging uv to sync inside the container
RUN uv venv && . .venv/bin/activate && uv pip install fastapi uvicorn asyncpg httpx google-cloud-documentai pydantic-settings cryptography supabase python-jose python-dotenv

EXPOSE 8000

CMD ["sh", "-c", ". .venv/bin/activate && uvicorn sage.main:app --host 0.0.0.0 --port 8000"]
