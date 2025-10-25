FROM python:3.11-slim

WORKDIR /app

RUN pip install pdm

COPY pyproject.toml pdm.lock ./
RUN pdm install --prod --no-editable

COPY ./db_service ./db_service
COPY .env .env

ENV PYTHONPATH=/app/db_service

