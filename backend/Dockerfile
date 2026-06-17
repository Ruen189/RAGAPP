FROM python:3.11-slim AS base
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY backend/tests ./tests
COPY knowledge_seed ./knowledge_seed

FROM base AS api
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS worker
CMD ["python", "-m", "app.worker"]
