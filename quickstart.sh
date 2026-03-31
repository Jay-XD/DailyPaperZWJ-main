#!/bin/bash
# Quick start script for Linux/macOS with Conda

set -euo pipefail

ENV_NAME="dailypaper"

echo "DailyPaper quick start"
echo

if ! command -v conda >/dev/null 2>&1; then
    echo "Conda is required but was not found."
    echo "Install Miniconda or Anaconda first, then rerun this script."
    exit 1
fi

if ! conda env list | awk '{print $1}' | grep -Fxq "${ENV_NAME}"; then
    echo "Creating Conda environment '${ENV_NAME}' from environment.yml ..."
    conda env create -f environment.yml
else
    echo "Conda environment '${ENV_NAME}' already exists."
fi

echo "Verifying core dependencies ..."
conda run -n "${ENV_NAME}" python -c "import yaml, arxiv, requests"

echo
echo "Running tests ..."
conda run -n "${ENV_NAME}" python -m unittest discover -s tests -v

echo
echo "Rebuilding paper metadata ..."
conda run -n "${ENV_NAME}" python scripts/reindex_papers.py

echo
echo "Generating static site ..."
conda run -n "${ENV_NAME}" python scripts/generate_html.py

echo
echo "Done."
echo "Preview locally with:"
echo "  conda run -n ${ENV_NAME} python -m http.server 8000 --directory docs"
echo "Then open http://127.0.0.1:8000"
