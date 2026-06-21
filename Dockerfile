# Gridlock — Parking Congestion Intelligence
# Containerises the live Streamlit app. The app reads the pre-built artifacts in
# outputs/ (zone parquet + CSVs + PNGs), so the 105 MB raw CSV is NOT needed in
# the image. To rebuild artifacts inside the container, mount the raw CSV and set
# GRIDLOCK_RAW_CSV, then run `python run_all.py`.

FROM python:3.12-slim

# system libs matplotlib/pyarrow may want at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# install deps first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# app code + config + pipeline + API + tests + pre-built artifacts
COPY config.py run_all.py api.py ./
COPY src/ ./src/
COPY tests/ ./tests/
COPY outputs/ ./outputs/
COPY data/ ./data/
COPY app.py ./

EXPOSE 8501 8000

# Streamlit listens on all interfaces inside the container
ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8501/_stcore/health').read()==b'ok' else 1)"

# Default: the dashboard app. Run the API instead with:
#   docker run -p 8000:8000 gridlock uvicorn api:app --host 0.0.0.0 --port 8000
CMD ["streamlit", "run", "app.py", "--server.port=8501"]
