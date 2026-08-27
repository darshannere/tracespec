FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN pip install --no-cache-dir . \
    && npm --prefix web install \
    && npm --prefix web run build

ENV TRACESPEC_DB_PATH=/data/tracespec.db

EXPOSE 8080

CMD ["tracespec", "serve", "--db", "/data/tracespec.db", "--host", "0.0.0.0", "--port", "8080"]
