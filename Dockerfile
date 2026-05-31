FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

EXPOSE 8099

CMD ["gunicorn", "--bind", "0.0.0.0:8099", "--workers", "2", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
