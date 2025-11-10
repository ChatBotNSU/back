FROM python:3.11-slim

WORKDIR /app

RUN pip install pdm

COPY pyproject.toml pdm.lock ./
RUN pdm install --prod --no-editable

COPY ./src ./src

ENV PYTHONPATH=/app/src
