FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y curl ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY rack_ai/requirements-production.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /tmp/requirements.txt

RUN groupadd --system --gid 10001 vision \
    && useradd --system --uid 10001 --gid vision --create-home vision
COPY --chown=vision:vision rack_ai /app/rack_ai
RUN mkdir -p /app/rack_ai/data /models && chown -R vision:vision /app/rack_ai/data /models

USER vision
ENV RACK_HOST=0.0.0.0
ENV RACK_PORT=8011
EXPOSE 8011
CMD ["python", "-m", "rack_ai.run"]
