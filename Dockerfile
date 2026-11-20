FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml requirements.txt requirements.lock ./
COPY src ./src
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY app.py ./
COPY .streamlit/config.toml .streamlit/config.toml
RUN useradd --create-home --uid 10001 amr && mkdir -p /data && chown amr:amr /data
USER amr
ENV AMR_DB_PATH=/data/evidence.sqlite3 AMR_READ_ONLY=true PYTHONUNBUFFERED=1
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3)"
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.headless=true"]
