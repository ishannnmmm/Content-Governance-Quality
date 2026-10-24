#!/usr/bin/env bash
# Starts the API with the environment the KB evaluation pipeline needs.
# Holds the real Groq key — it is listed in .gitignore; keep it that way.
set -euo pipefail

export GROQ_API_KEY="${GROQ_API_KEY:-gsk_...}"
export KB_FILE="${KB_FILE:-/Users/imisra/Documents/VA_Analysis/TGR/kb_articles.csv}"
export BOT_FLOW_FILE="${BOT_FLOW_FILE:-/Users/imisra/Documents/VA_Analysis/TGR/bot_flows_tgr.csv}"
export PIPELINE_DIR="${PIPELINE_DIR:-$(cd "$(dirname "$0")" && pwd)}"
export MPLBACKEND=Agg
# Your Groq tier's per-minute limits — LLM calls are paced to stay under them.
export GROQ_RPM="${GROQ_RPM:-30}"
export GROQ_TPM="${GROQ_TPM:-8000}"
# Optional: questions written from article titles → enables retrieval-gap detection
# export LABELLED_SET_FILE=/path/to/labelled_questions.csv

cd "$(dirname "$0")"
exec python api_server.py
