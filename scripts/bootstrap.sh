#!/usr/bin/env bash
set -euo pipefail

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "Bootstrap complete. Next: cp config.example.yaml config.yaml && cp .env.example .env"