#!/usr/bin/env python3
"""
run_full_pipeline.py
━━━━━━━━━━━━━━━━━━━━
End-to-end KB evaluation from the command line, without the API server:

    raw transcripts → extract questions → canonical questions with counts
    → retrieve + rerank → judge → classify failure → rank by frequency

Usage:
    1. Edit the PATHS section below to point at your files.
    2. Set GROQ_API_KEY in your shell — the judge needs it:
           export GROQ_API_KEY="gsk_..."
    3. Run Step 0 first if you have not:
           python diagnose_kb.py /path/to/kb_articles.csv /path/to/bot_flows_tgr.csv
    4. Run:
           python run_full_pipeline.py

Requirements:
    pip install -r requirements.txt
"""

import os
import sys
import time

# ═════════════════════════════════════════════════════════════
# PATHS — EDIT THESE BEFORE RUNNING
# ═════════════════════════════════════════════════════════════

# Raw transcript CSV (full session per row, with chatOfferAccepted column)
RAW_TRANSCRIPT_FILE = "/Users/imisra/Documents/VA_Analysis/TGR/Book23.csv"

# KB and bot-flow reference files
KB_FILE       = "/Users/imisra/Documents/VA_Analysis/TGR/kb_articles.csv"
BOT_FLOW_FILE = "/Users/imisra/Documents/VA_Analysis/TGR/bot_flows_tgr.csv"

# Output directory (created automatically)
OUTPUT_DIR    = "/Users/imisra/Documents/VA_Analysis/TGR/pipeline_output"

# Column names in your raw transcript CSV
UTTERANCE_COL  = "utterance"        # column with the full transcript blob
ESCALATION_COL = "chatOfferAccepted"  # column with escalation flag

# Optional: labelled questions for measuring retrieval gaps (see metrics.py)
LABELLED_SET_FILE = os.environ.get("LABELLED_SET_FILE", "")

# Tuning constants live in eval_config.py.

# ═════════════════════════════════════════════════════════════


def check_prerequisites():
    """Verify input files exist and the API key is set."""
    missing = [f for f in [RAW_TRANSCRIPT_FILE, KB_FILE] if not os.path.exists(f)]
    if missing:
        print(f"\n❌  Missing input files:")
        for f in missing:
            print(f"    • {f}")
        print("\n    Update the PATHS section at the top of run_full_pipeline.py")
        sys.exit(1)

    if not os.environ.get("GROQ_API_KEY"):
        print("❌  GROQ_API_KEY not set — coverage is decided by an LLM judge.")
        print('    export GROQ_API_KEY="gsk_..."')
        sys.exit(1)


def main():
    import pandas as pd

    print("=" * 65)
    print("  KB EVALUATION — Full Pipeline")
    print("=" * 65)

    check_prerequisites()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    t0 = time.time()

    # ── Extract questions ─────────────────────────────────────
    print("\n" + "─" * 65)
    print("  Extract questions")
    print("─" * 65)

    from preprocess_transcripts import preprocess
    from utterance_quality import collect_speaker_names, strip_menu_clicks, strip_system_messages

    questions_path = os.path.join(OUTPUT_DIR, "customer_utterances.csv")
    preprocess(
        input_path=RAW_TRANSCRIPT_FILE,
        output_path=questions_path,
        utterance_col=UTTERANCE_COL,
        escalation_col=ESCALATION_COL,
    )
    extracted = strip_system_messages(pd.read_csv(questions_path), text_col="utterance")
    filtered, _ = strip_menu_clicks(extracted, text_col="utterance")
    filtered.to_csv(questions_path, index=False)

    from improved_coverage_analysis import scrub_denylist

    raw = pd.read_csv(RAW_TRANSCRIPT_FILE, encoding="utf-8-sig")
    names = scrub_denylist(collect_speaker_names(raw[UTTERANCE_COL]), KB_FILE)

    # ── Evaluate ──────────────────────────────────────────────
    print("\n" + "─" * 65)
    print("  Group, retrieve, judge")
    print("─" * 65)

    import improved_coverage_analysis as s2
    import improved_utterance_analysis as s1

    cfg = {**s1.CFG, "INPUT_FILE": questions_path, "OUTPUT_DIR": OUTPUT_DIR}
    df = s1.load_data(cfg)
    embeddings = s1.embed(df, cfg)
    result = s2.run_evaluation(
        df, embeddings, KB_FILE, BOT_FLOW_FILE, OUTPUT_DIR,
        names=names, labelled_file=LABELLED_SET_FILE or None,
    )

    from metrics import run_aggregates

    summary = run_aggregates(result["questions"], result["retrievalMeasured"])

    # ── Done ──────────────────────────────────────────────────
    elapsed = round(time.time() - t0, 1)

    print("\n" + "=" * 65)
    print(f"  ✅  Pipeline complete in {elapsed}s")
    print("=" * 65)
    for key, value in summary.items():
        print(f"    {key:<20} {value}")
    print(f"\n📁  Outputs in: {OUTPUT_DIR}/")
    print("    customer_utterances.csv     — Extracted questions with bot responses")
    print("    utterance_embeddings.npy    — Cached question embeddings")
    print("    question_evaluation.json    — One record per canonical question")
    print("    question_evaluation.csv     — Same, flattened for spreadsheets\n")


if __name__ == "__main__":
    main()
