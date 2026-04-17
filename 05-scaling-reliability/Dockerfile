# ============================================================
# Dockerfile cho 05-scaling-reliability
# Build context: project root (day12_ha-tang-cloud_va_deployment/)
#
# Build: docker compose -f 05-scaling-reliability/production/docker-compose.yml up --scale agent=3
# ============================================================

FROM python:3.11-slim

WORKDIR /app

# Cài dependencies
COPY 05-scaling-reliability/develop/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir redis

# Copy application code
COPY 05-scaling-reliability/production/app.py app.py
COPY 05-scaling-reliability/production/utils/ utils/

EXPOSE 8000

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

CMD ["python", "app.py"]
