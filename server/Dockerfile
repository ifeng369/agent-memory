FROM python:3.11-slim AS builder

ARG HF_ENDPOINT=https://hf-mirror.com
ENV HF_ENDPOINT=$HF_ENDPOINT

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir torch==2.2.0 --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt requirements-build.txt .
RUN pip install --no-cache-dir -r requirements-build.txt
COPY export_model.py .
RUN python export_model.py \
    && rm -rf /root/.cache/huggingface /app/models/models--*

FROM python:3.11-slim AS runtime

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=builder /app/models/agent-memory-onnx /app/models/agent-memory-onnx
COPY src/ ./src/
COPY web/ ./web/
COPY init.sql .
RUN mkdir -p /app/logs

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3000/api/health || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "3000"]
