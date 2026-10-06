FROM python:3.12-slim@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy PATH=/app/.venv/bin:$PATH
RUN pip install --no-cache-dir uv==0.11.3
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev
ENTRYPOINT ["bikeplan"]
