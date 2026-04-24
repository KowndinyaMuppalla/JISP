#!/usr/bin/env bash
# Launch the JISP management demo dashboard (Streamlit).
#
# Assumes the JISP API is already running on localhost:8000 and Ollama is up
# with llama3.2 pulled. See README.md "Run the management demo" section.
set -euo pipefail

cd "$(dirname "$0")/.."

export PYTHONPATH="${PYTHONPATH:-$PWD}"
export JISP_API_BASE_URL="${JISP_API_BASE_URL:-http://localhost:8000}"
export JISP_OLLAMA_MODEL="${JISP_OLLAMA_MODEL:-llama3.2}"
exec streamlit run ui/dashboards/streamlit_app.py \
  --server.port "${JISP_UI_PORT:-8501}" \
  --server.address "${JISP_UI_HOST:-0.0.0.0}" \
  --browser.gatherUsageStats false
