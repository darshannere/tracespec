FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN pip install --no-cache-dir . \
    && if [ -f web/package.json ]; then \
        npm --prefix web install \
        && npm --prefix web run build \
        && python -c 'import shutil, sysconfig; from pathlib import Path; source = Path("web/dist"); target = Path(sysconfig.get_path("purelib")) / "web" / "dist"; target.parent.mkdir(parents=True, exist_ok=True); shutil.copytree(source, target, dirs_exist_ok=True)'; \
    fi

ENV TRACESPEC_DB_PATH=/data/tracespec.db

EXPOSE 8080

CMD ["tracespec", "serve", "--db", "/data/tracespec.db", "--host", "0.0.0.0", "--port", "8080"]
