#!/usr/bin/env bash
# Run LegalEase.AI with the project venv (macOS/Linux)
cd "$(dirname "$0")"
exec ./venv/bin/streamlit run app.py
