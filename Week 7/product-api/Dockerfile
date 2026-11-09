FROM python:3.12-slim AS builder
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY pyproject.toml requirements.txt ./
COPY src ./src
RUN pip install --no-cache-dir .

FROM python:3.12-slim AS runtime
WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --home /app app \
    && mkdir /app/instance && chown app:app /app/instance
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY --from=builder /opt/venv /opt/venv
COPY wsgi.py gunicorn.conf.py ./
USER app
EXPOSE 5000
HEALTHCHECK --interval=15s --timeout=3s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/healthz', timeout=2)"]
CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]
