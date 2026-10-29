FROM python:3.12-slim

WORKDIR /app

# [MEMO-PDF v2] WeasyPrint : Pango/HarfBuzz + polices. fonts-noto-cjk = Noto Sans CJK (kanji du
# dossier « Kanji utiles ») ; fonts-noto-color-emoji = les 📅 📁 📍 du gabarit print.html ;
# fonts-dejavu-core = ☐ ☑ et repli latin.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libffi8 \
      fonts-noto-cjk fonts-noto-color-emoji fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

EXPOSE 8099
EXPOSE 8100

# [DASH-MCP] deux workers (gunicorn 8099 + uvicorn 8100), voir bin/start.sh
RUN chmod +x /app/bin/start.sh
CMD ["/app/bin/start.sh"]
