#!/usr/bin/env python3
"""
preprocess_transcripts.py
━━━━━━━━━━━━━━━━━━━━━━━━━
Extracts individual customer utterances from raw eGain/TGR conversation
transcripts where each CSV row holds an entire session.

Input format (CSV):
    - Column "utterance": full transcript blob with timestamped turns like
          2026-08-17 11:59:19 Krystal King: Make Payment
          2026-08-17 11:59:22 Jordan (bot): To assist with this topic...
    - Column "chatOfferAccepted": escalation flag per session (TRUE/FALSE/1/0)

Output format (CSV):
    session_id | utterance | bot_response | chatOfferAccepted [| outcome] [| routed_intent]
    One row per customer utterance, linked back to its session.
    bot_response holds the bot turns that followed the utterance — they are
    evidence of what the customer was actually told. outcome and
    routed_intent are carried through when the export has them.

Usage:
    python preprocess_transcripts.py input.csv [output.csv]
    python preprocess_transcripts.py input.csv output.csv --utterance-col utterance --escalation-col chatOfferAccepted

Can also be imported:
    from preprocess_transcripts import preprocess
    df = preprocess("input.csv", "output.csv")
"""

import re
import sys
import argparse
import pandas as pd

# ─────────────────────────────────────────────────────────────
# PATTERNS
# ─────────────────────────────────────────────────────────────

# Matches timestamps like "2026-08-17 12:01:49" or "2026-08-17 12:01:57.118"
TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?")

# Splits a transcript blob right before each timestamp
SPLIT_RE = re.compile(r"(?=\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?\s)")

# Identifies bot turns: speaker name contains "(bot)"
BOT_RE = re.compile(r"\(bot\)", re.IGNORECASE)

# Live-agent and system turns: "Waynesha (AGENT)", "system (SYSTEM)".
# Neither is a customer question; agent turns are not bot evidence either.
NON_CUSTOMER_RE = re.compile(r"\((?:agent|system)\)", re.IGNORECASE)

# Noise utterances to drop — exact match after lowering/stripping
NOISE_EXACT = {
    "yes", "no", "yeah", "yep", "yea", "nope", "nah",
    "ok", "okay", "k", "sure", "alright",
    "thanks", "thank you", "ty", "thx",
    "bye", "goodbye", "bye bye",
    "hi", "hello", "hey", "hii", "helo",
}

# Session-level columns carried through to the output when present.
OUTCOME_CANDIDATES = ("outcome", "conversationOutcome", "resolution", "disposition")
ROUTED_INTENT_CANDIDATES = ("routedIntent", "routed_intent", "intentName", "intent_name", "intent")


# ─────────────────────────────────────────────────────────────
# CORE EXTRACTION
# ─────────────────────────────────────────────────────────────

def extract_turns(transcript_text: str) -> list[dict]:
    """
    Parse a raw transcript blob into customer messages, each paired with
    the bot's reply.

    Logic:
      1. Split on timestamp boundaries → one chunk per turn
      2. Strip the leading timestamp from each chunk
      3. Separate "Speaker: message"
      4. Bot turns (speaker contains "(bot)") are attached as bot_response
         to the customer message they follow — not discarded. Live-agent
         and system turns ("(AGENT)", "(SYSTEM)") are dropped
      5. Drop empty, noise-only, or too-short customer messages (and the
         bot replies to them)
      6. Drop messages that are just the start of another timestamp
         (happens when a customer turn has no actual content)
    """
    if not transcript_text or not isinstance(transcript_text, str):
        return []

    chunks = SPLIT_RE.split(transcript_text)
    turns: list[dict] = []
    # Bot replies go to the most recent kept customer message. After a
    # dropped one ("ok", "yes") they have no question to attach to.
    current: dict | None = None

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue

        # Strip the leading timestamp
        m = TIMESTAMP_RE.match(chunk)
        if not m:
            continue  # pre-timestamp text, skip

        rest = chunk[m.end():].strip()
        if not rest:
            continue

        # Split on first ": " to get speaker and message
        speaker, sep, message = rest.partition(": ")
        if not sep:
            continue  # no colon delimiter found

        speaker = speaker.strip()
        message = message.strip()

        # ── Bot turns: keep as evidence of what the customer was told ──
        if BOT_RE.search(speaker):
            if current is not None and message and not TIMESTAMP_RE.match(message):
                current["bot_response"].append(message)
            continue

        # ── Agent / system turns: not questions, not bot replies ──
        if NON_CUSTOMER_RE.search(speaker):
            current = None
            continue

        current = None

        # ── Filter: empty message ────────────────────────────
        if not message:
            continue

        # ── Filter: message is just another timestamp ────────
        # This happens when the customer's "turn" was empty and
        # the next turn's timestamp got captured as the message.
        if TIMESTAMP_RE.match(message):
            continue

        # ── Filter: noise / filler ───────────────────────────
        cleaned = message.lower().strip().rstrip(".!?,")
        if cleaned in NOISE_EXACT:
            continue

        # ── Filter: very short (≤ 2 chars) ───────────────────
        if len(cleaned) <= 2:
            continue

        current = {"utterance": message, "bot_response": []}
        turns.append(current)

    for turn in turns:
        turn["bot_response"] = "\n".join(turn["bot_response"])
    return turns


def extract_customer_utterances(transcript_text: str) -> list[str]:
    """Customer messages only, without the bot replies."""
    return [t["utterance"] for t in extract_turns(transcript_text)]


def _find_col(df: pd.DataFrame, wanted: str | None, candidates: tuple[str, ...]) -> str | None:
    """Exact column if named, else the first case-insensitive candidate match."""
    lower = {c.lower(): c for c in df.columns}
    for name in ((wanted,) if wanted else candidates):
        if name in df.columns:
            return name
        if name.lower() in lower:
            return lower[name.lower()]
    return None


# ─────────────────────────────────────────────────────────────
# FILE-LEVEL PREPROCESSING
# ─────────────────────────────────────────────────────────────

def preprocess(
    input_path: str,
    output_path: str,
    utterance_col: str = "utterance",
    escalation_col: str = "chatOfferAccepted",
    outcome_col: str | None = None,
    routed_intent_col: str | None = None,
) -> pd.DataFrame:
    """
    Read a CSV of raw session transcripts and produce a one-utterance-per-row CSV.

    Parameters
    ----------
    input_path : str
        Path to the raw transcript CSV.
    output_path : str
        Path for the output CSV.
    utterance_col : str
        Column name containing the transcript blob.
    escalation_col : str
        Column name containing the escalation flag.
    outcome_col, routed_intent_col : str, optional
        Session-level outcome (self-served / abandoned / escalated) and the
        bot flow the session was routed to. Auto-detected by common names
        when not given; written out as `outcome` and `routed_intent`.

    Returns
    -------
    pd.DataFrame
        The extracted utterances dataframe.
    """
    print("📂  Loading raw transcripts...")
    df = pd.read_csv(input_path, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()

    # Verify expected columns exist
    if utterance_col not in df.columns:
        matches = [c for c in df.columns if c.lower() == utterance_col.lower()]
        if matches:
            utterance_col = matches[0]
        else:
            print(f"❌  Column '{utterance_col}' not found. Available: {list(df.columns)}")
            sys.exit(1)

    has_escalation = escalation_col in df.columns
    if not has_escalation:
        matches = [c for c in df.columns if c.lower() == escalation_col.lower()]
        if matches:
            escalation_col = matches[0]
            has_escalation = True
        else:
            print(f"  ⚠️  Column '{escalation_col}' not found — defaulting to FALSE")

    outcome_col = _find_col(df, outcome_col, OUTCOME_CANDIDATES)
    routed_intent_col = _find_col(df, routed_intent_col, ROUTED_INTENT_CANDIDATES)
    for label, col in (("outcome", outcome_col), ("routed intent", routed_intent_col)):
        print(f"    {label.capitalize()} column: {col or 'not in this export'}")

    print(f"    Raw sessions: {len(df):,}")

    rows = []
    empty_sessions = 0

    for idx, row in df.iterrows():
        transcript = str(row.get(utterance_col, ""))
        escalated = row.get(escalation_col, "FALSE") if has_escalation else "FALSE"

        turns = extract_turns(transcript)

        if not turns:
            empty_sessions += 1
            continue

        for turn in turns:
            out = {
                "session_id": int(idx) + 1,
                "utterance": turn["utterance"],
                "bot_response": turn["bot_response"],
                "chatOfferAccepted": escalated,
            }
            if outcome_col:
                out["outcome"] = row.get(outcome_col)
            if routed_intent_col:
                out["routed_intent"] = row.get(routed_intent_col)
            rows.append(out)

    result = pd.DataFrame(rows)
    result.to_csv(output_path, index=False)

    n_sessions = len(df) - empty_sessions
    print(f"    Sessions with customer utterances: {n_sessions:,}")
    print(f"    Sessions with no extractable content: {empty_sessions:,}")
    print(f"    Total customer utterances extracted: {len(result):,}")
    print(f"    Avg utterances per session: {len(result) / max(n_sessions, 1):.1f}")
    print(f"✅  Output → {output_path}")

    return result


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Extract customer utterances from raw chat transcripts"
    )
    parser.add_argument("input", help="Path to raw transcript CSV")
    parser.add_argument("output", nargs="?", default=None,
                        help="Output CSV path (default: <input>_preprocessed.csv)")
    parser.add_argument("--utterance-col", default="utterance",
                        help="Column containing transcript blobs")
    parser.add_argument("--escalation-col", default="chatOfferAccepted",
                        help="Column containing escalation flag")
    parser.add_argument("--outcome-col", default=None,
                        help="Column containing session outcome (auto-detected if omitted)")
    parser.add_argument("--routed-intent-col", default=None,
                        help="Column containing routed bot flow (auto-detected if omitted)")

    args = parser.parse_args()
    out = args.output or args.input.rsplit(".", 1)[0] + "_preprocessed.csv"

    preprocess(args.input, out, args.utterance_col, args.escalation_col,
               args.outcome_col, args.routed_intent_col)


if __name__ == "__main__":
    main()
