# Reus-Veritas OS — multi-stage production image
# Stage 1: build dependencies in an environment isolated from the final runtime image
FROM python:3.12-slim AS builder

WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock .
RUN pip install --no-cache-dir --user -r requirements.lock

# Stage 2: runtime image — no build tools, non-root user, smaller layers
FROM python:3.12-slim AS runtime

RUN groupadd --gid 1000 reus && \
    useradd --uid 1000 --gid reus --shell /bin/bash --create-home reus

WORKDIR /app
COPY --from=builder /root/.local /home/reus/.local
COPY --chown=reus:reus . .

ENV PATH=/home/reus/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER reus

EXPOSE 8000

# /health is deliberately cheap — suitable for a container engine's liveness probe without stressing the service
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
