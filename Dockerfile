FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

EXPOSE 8099
EXPOSE 8100

# [DASH-MCP] deux workers (gunicorn 8099 + uvicorn 8100), voir bin/start.sh
RUN chmod +x /app/bin/start.sh
CMD ["/app/bin/start.sh"]
