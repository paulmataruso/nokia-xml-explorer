# syntax=docker/dockerfile:1

# ---- Stage 1: build the React frontend ----
FROM node:20-alpine AS frontend-build
WORKDIR /build
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python backend runtime, serving the built frontend too ----
FROM python:3.12-slim AS runtime
WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY --from=frontend-build /build/dist ./frontend_dist
COPY example ./example

ENV SCP_DIR=/data/scp \
    EXAMPLE_DIR=/app/example \
    FRONTEND_DIST=/app/frontend_dist \
    PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
