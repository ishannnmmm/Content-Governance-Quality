#!/usr/bin/env python3
"""
pii_scrubber.py
━━━━━━━━━━━━━━━
Strips personally identifiable information from customer utterances
before any data is sent to an external LLM.

What it catches:
  • Names (replaced with [CUSTOMER])
  • Email addresses → [EMAIL]
  • Phone numbers (US formats) → [PHONE]
  • Policy / account numbers (digit sequences 6+ digits) → [ACCOUNT_NUM]
  • SSN patterns → [SSN]
  • Street addresses (partial — number + street name patterns) → [ADDRESS]
  • URLs with personal paths → [URL]
  • Credit card patterns (13-19 digits) → [CARD_NUM]
  • Dates of birth in common formats → [DOB]

Design:
  This runs LOCALLY before any LLM call. The scrubbed text is what
  gets sent to the API. Raw PII never leaves your machine.

  The scrubber is intentionally aggressive — it's better to over-redact
  than to leak PII. Clustering and similarity matching happen on the
  raw text locally, so redaction doesn't affect analytical accuracy.

Usage:
    from pii_scrubber import scrub, scrub_series

    clean = scrub("My name is John Smith and my email is john@gmail.com")
    # → "My name is [CUSTOMER] and my email is [EMAIL]"

    df["safe_text"] = scrub_series(df["utterance"])
"""

import re
import pandas as pd

# ─────────────────────────────────────────────────────────────
# PATTERNS (ordered by specificity — more specific first)
# ─────────────────────────────────────────────────────────────

_PATTERNS = [
    # SSN: 123-45-6789 or 123 45 6789
    (re.compile(r"\b\d{3}[-\s]\d{2}[-\s]\d{4}\b"), "[SSN]"),

    # Credit card: 13-19 digits, optionally grouped with spaces/dashes
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[CARD_NUM]"),

    # Email
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),

    # URL (catches https://... and www....)
    (re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE), "[URL]"),

    # US phone: (800) 555-1234, 800-555-1234, 800.555.1234, 8005551234, +1-800...
    (re.compile(
        r"(?:\+?1[-.\s]?)?"                   # optional +1
        r"(?:\(?\d{3}\)?[-.\s]?)"              # area code
        r"\d{3}[-.\s]?\d{4}\b"                 # 7 digits
    ), "[PHONE]"),

    # Date of birth patterns: MM/DD/YYYY, MM-DD-YYYY, Month DD YYYY
    (re.compile(
        r"\b(?:0?[1-9]|1[0-2])[/\-](?:0?[1-9]|[12]\d|3[01])[/\-](?:19|20)\d{2}\b"
    ), "[DOB]"),
    (re.compile(
        r"\b(?:January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+\d{1,2},?\s+\d{4}\b",
        re.IGNORECASE
    ), "[DOB]"),

    # Policy / account numbers: 6+ digit sequences (after other patterns removed)
    (re.compile(r"\b\d{6,}\b"), "[ACCOUNT_NUM]"),

    # Street address: "123 Main St" or "456 Elm Avenue" patterns
    (re.compile(
        r"\b\d{1,5}\s+[A-Za-z]+\s+"
        r"(?:St(?:reet)?|Ave(?:nue)?|Blvd|Boulevard|Dr(?:ive)?|"
        r"Rd|Road|Ln|Lane|Way|Ct|Court|Pl(?:ace)?|Cir(?:cle)?)\b",
        re.IGNORECASE
    ), "[ADDRESS]"),
]

# Name patterns — applied last because they're the most ambiguous.
# We catch "First Last" patterns where both words are title-cased
# and at least 2 chars each, not preceded by common non-name contexts.
_NAME_PATTERN = re.compile(
    r"\b([A-Z][a-z]{1,20})\s+([A-Z][a-z]{1,20}(?:\s+[A-Z][a-z]{1,20})?)\b"
)

# Words that look like names but aren't (add to this as needed)
_NAME_EXCEPTIONS = {
    "the general", "make payment", "billing and", "claims related",
    "policy coverage", "additional questions", "additional policy",
    "related questions", "coverage questions", "reinstatement questions",
    "virtual assistant", "chat session", "privacy policy",
    "business hours", "contact details",
}


# ─────────────────────────────────────────────────────────────
# SCRUBBING FUNCTIONS
# ─────────────────────────────────────────────────────────────

def replace_name(match):
    """Keep known non-name phrases ("Make Payment"); redact everything else."""
    full = match.group(0).lower()
    if full in _NAME_EXCEPTIONS:
        return match.group(0)  # keep it
    return "[CUSTOMER]"


def scrub(text: str, extra_names: set[str] | None = None) -> str:
    """
    Remove PII from a single text string. Returns scrubbed copy.

    extra_names is a denylist of known speaker names (from
    collect_speaker_names). It is matched case-insensitively and catches
    what _NAME_PATTERN cannot: lowercased text and bare first names.
    """
    if not text or not isinstance(text, str):
        return text

    result = text

    # Apply regex patterns in order
    for pattern, replacement in _PATTERNS:
        result = pattern.sub(replacement, result)

    # Known speaker names, case-insensitive, whole words only.
    if extra_names:
        for name in sorted(extra_names, key=len, reverse=True):
            if len(name) < 3:
                continue  # too short to match safely
            result = re.sub(rf"\b{re.escape(name)}\b", "[CUSTOMER]",
                            result, flags=re.IGNORECASE)

    # Name scrubbing (more conservative — only clear "First Last" patterns)
    result = _NAME_PATTERN.sub(replace_name, result)

    # Clean up repeated placeholders
    result = re.sub(r"(\[CUSTOMER\]\s*){2,}", "[CUSTOMER] ", result)

    return result.strip()


def scrub_series(series: pd.Series, extra_names: set[str] | None = None) -> pd.Series:
    """Scrub PII from an entire pandas Series. Returns new Series."""
    return series.fillna("").astype(str).apply(lambda t: scrub(t, extra_names=extra_names))


# ─────────────────────────────────────────────────────────────
# CLI — test scrubbing on sample input
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_cases = [
        "My name is John Smith and my policy is 1234567",
        "Call me at 800-555-1234 or email john.doe@gmail.com",
        "I live at 456 Oak Drive and my SSN is 123-45-6789",
        "My DOB is 03/15/1985 and my card is 4111 1111 1111 1111",
        "Make Payment",  # should NOT be scrubbed
        "Billing and Reinstatement Questions",  # should NOT be scrubbed
        "I need to file a claim for my accident on January 5, 2026",
        "Can you check account 98765432 for Krystal King",
    ]

    # Lowercased bare first names only get caught via the speaker denylist.
    test_cases.append("hi this is waynesha, krystal said to ask about my bill")
    names = {"waynesha", "krystal", "king"}

    print("PII Scrubber — Test Cases\n")
    for text in test_cases:
        cleaned = scrub(text, extra_names=names)
        print(f"  IN:  {text}")
        print(f"  OUT: {cleaned}")
        print()
