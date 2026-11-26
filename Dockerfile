FROM node:24-bookworm-slim AS frontend
WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.14-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements-web.txt ./
RUN pip install --no-cache-dir -r requirements-web.txt
COPY echelon/ ./echelon/
COPY examples/ ./examples/
COPY --from=frontend /build/web/dist/ ./web/dist/
EXPOSE 10000
CMD ["sh", "-c", "uvicorn echelon.web_api:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1"]
