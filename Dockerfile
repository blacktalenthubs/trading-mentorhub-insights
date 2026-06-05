# ── Stage 1: build the React frontend ──────────────────────────────
# web/dist is gitignored (built here, never committed). FastAPI serves it from
# /app/web/dist, so it must exist in the final image — otherwise the SPA route
# is skipped and "/" returns FastAPI's {"detail":"Not Found"}.
FROM node:20-slim AS frontend
WORKDIR /web
# Install deps first (cached unless the lockfile changes), then build.
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build          # → /web/dist

# ── Stage 2: Python app (FastAPI + Streamlit) ──────────────────────
FROM python:3.13-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Bring in the compiled frontend from stage 1. web/dist is gitignored, so it is
# NOT included by `COPY . .` above — it must come from the build stage.
COPY --from=frontend /web/dist ./web/dist

# Expose port (Railway sets $PORT)
EXPOSE 8080

# Run Streamlit (the FastAPI service overrides this with a uvicorn start command)
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
