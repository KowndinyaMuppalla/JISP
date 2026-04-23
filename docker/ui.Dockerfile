# JISP UI container — Streamlit management demo dashboard.
#
# The UI is visualization-only (see ADR 001). It does not import from
# spatial/, timeseries/, geoai/, or ingestion/. It talks to the API
# container over HTTP via JISP_API_BASE_URL (defaults to http://api:8000
# inside the compose network).
#
# Build context: the repository root (see docker/docker-compose.yml).

FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

# Streamlit needs the UI module plus the schemas it references indirectly
# for clarity. The dashboard itself only imports from ui/.
COPY ui/ ./ui/

RUN useradd --system --create-home --shell /usr/sbin/nologin jisp
USER jisp

EXPOSE 8501

# `--server.address 0.0.0.0` is required so the host can reach the
# container via the published port. Usage stats pings are disabled so the
# container works on air-gapped demos.
CMD ["streamlit", "run", "ui/dashboards/streamlit_app.py", \
     "--server.address", "0.0.0.0", \
     "--server.port", "8501", \
     "--browser.gatherUsageStats", "false"]
