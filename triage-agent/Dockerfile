FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg2-binary (libpq) — already bundled in the wheel
# but better to be explicit for any native compiles.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./
COPY migrations ./migrations

# Cursor + audit log live in /data; mount a Railway volume here so they
# survive restarts.
RUN mkdir -p /data
ENV TRIAGE_CURSOR_FILE=/data/triage-cursor
ENV TRIAGE_AUDIT_FILE=/data/triage-audit.jsonl

CMD ["python", "-u", "live.py"]
