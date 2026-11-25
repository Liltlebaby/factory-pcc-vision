FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY PCC/integrations/pond_gateway/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --requirement requirements.txt \
    && addgroup --system gateway \
    && adduser --system --ingroup gateway --home /app gateway
COPY PCC/integrations/pond_gateway/pond_gateway ./pond_gateway
RUN mkdir -p /data && chown -R gateway:gateway /app /data
USER gateway

CMD ["python", "-m", "pond_gateway.main"]
