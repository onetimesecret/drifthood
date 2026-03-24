# Stage 1: Build frontend
FROM node:22-alpine AS frontend
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm run build

# Stage 2: Python runtime
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY dd/ dd/
COPY run.py .
COPY --from=frontend /app/dist dist/
RUN mkdir -p data
VOLUME /app/data
EXPOSE 8899
CMD ["python", "run.py"]
