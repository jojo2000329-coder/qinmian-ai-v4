FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    TZ=Asia/Shanghai

WORKDIR /app

COPY requirements-runtime.txt .
RUN pip install --no-cache-dir -r requirements-runtime.txt

COPY app.py ./
COPY qinmian ./qinmian
COPY static ./static
COPY data ./data

RUN mkdir -p /app/data/conversations /app/data/knowledge_base \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8080')+'/health', timeout=3)" || exit 1

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 8 --timeout 120 --access-logfile - --error-logfile - app:app"]
