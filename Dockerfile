FROM node:26-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /workspace
COPY backend/requirements-ai.txt /workspace/backend/requirements-ai.txt
RUN pip install --no-cache-dir --require-hashes -r backend/requirements-ai.txt
COPY backend/app /workspace/backend/app
COPY backend/scripts /workspace/backend/scripts
COPY backend/alembic /workspace/backend/alembic
COPY backend/alembic.ini /workspace/backend/alembic.ini
COPY --from=frontend /frontend/dist /workspace/frontend/dist
RUN useradd --create-home shop && mkdir -p /workspace/data && chown -R shop:shop /workspace/data
USER shop
WORKDIR /workspace/backend
ENV KCD_MODE=demo
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
