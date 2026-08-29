FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    LOG_DIR=/app/logs

EXPOSE 9093

CMD ["python", "-m", "agent.main"]
