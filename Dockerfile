FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt \
    && useradd --create-home --uid 10001 appuser
COPY --chown=appuser:appuser src ./src
COPY --chown=appuser:appuser scripts ./scripts
COPY --chown=appuser:appuser sql ./sql
COPY --chown=appuser:appuser data ./data
RUN mkdir /app/.local && chown appuser:appuser /app/.local
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=6s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=5)"
CMD ["python", "-m", "uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
