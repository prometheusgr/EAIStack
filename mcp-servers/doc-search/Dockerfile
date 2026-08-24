FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY . .
RUN pip install --no-cache-dir -e .
RUN chmod +x docker-entrypoint.sh

EXPOSE 8100

ENTRYPOINT ["./docker-entrypoint.sh"]
