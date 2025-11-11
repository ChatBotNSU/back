FROM python:3.11-slim

RUN pip install --no-cache-dir --upgrade pip

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY runner.py /app/runner.py

RUN useradd -m -u 1000 runner
USER runner

EXPOSE 8080
ENTRYPOINT ["python", "/app/runner.py"]
