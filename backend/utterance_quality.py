"""
utterance_quality.py
━━━━━━━━━━━━━━━━━━━━
Two problems this solves.

PROBLEM 1 — Menu clicks pollute the clusters.
─────────────────────────────────────────────
In eGain/TGR transcripts, a customer tapping a bot menu button is logged
exactly like a typed message:

    2026-08-17 11:59:19 Krystal King: Make Payment
    2026-08-17 12:03:11 Krystal King: Billing and Reinstatement Questions

"Make Payment" is not a question — it's a button label, and it appears
verbatim in thousands of sessions. Typed questions are all slightly
different from one another; menu labels are byte-identical every time.
So clustering locks onto the menu labels and the real questions get
buried. That's why cluster summaries read like a navigation menu.

We detect these WITHOUT a hardcoded list, because the menu changes and
every deployment has different buttons. The signal is statistical:

    • the exact string repeats far more often than any human phrasing
    • it's short
    • it's Title Case or otherwise not sentence-like
    • it has no question mark, no first-person pronoun, no typos

PROBLEM 2 — "Top themes" are keyword soup.
──────────────────────────────────────────
TF-IDF gives you "payment, charge, refund", which tells a reader almost
nothing. People want to see what customers actually asked.

So we pick REPRESENTATIVE utterances instead: the ones closest to the
cluster's centre in embedding space, de-duplicated so you get several
genuinely different questions rather than five rewordings of one.
"""

from __future__ import annotations

import re
from typing import List, Optional

import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────
# MENU-CLICK DETECTION
# ─────────────────────────────────────────────────────────────

# A typed question usually has at least one of these.
_HUMAN_SIGNALS = re.compile(
    r"\?|\b(i|my|me|we|our|you|your)\b|\b(can|could|would|will|do|does|did|is|are|"
    r"how|what|when|where|why|who|need|want|trying|please|help)\b",
    re.IGNORECASE,
)

# Title Case Like This — typical of button labels.
_TITLE_CASE = re.compile(r"^(?:[A-Z][a-z0-9]*|and|or|the|of|to|for|a|an|&)(?:\s+(?:[A-Z][a-z0-9]*|and|or|the|of|to|for|a|an|&))*$")


def _looks_like_button(text: str) -> bool:
    """Shape-based check: does this read like a UI label rather than a sentence?"""
    t = text.strip()
    if not t:
        return False
    if len(t) > 60:
        return False
    if "?" in t:
        return False
    words = t.split()
    if len(words) > 7:
        return False
    if _TITLE_CASE.match(t):
        return True
    # ALL CAPS labels
    if t.isupper() and len(words) <= 5:
        return True
    return False


def detect_menu_labels(
    utterances: pd.Series,
    min_repeat_ratio: float = 0.004,
    min_absolute_count: int = 15,
) -> List[str]:
    """
    Find strings that behave like menu buttons rather than typed messages.

    A string is flagged when it repeats unusually often AND looks like a
    label AND lacks the markers of human writing. All three must hold, so
    a genuinely common question ("how do i pay my bill?") is kept — it has
    a question mark and a first-person pronoun.

    Parameters
    ----------
    min_repeat_ratio : float
        Fraction of all utterances a string must hit to count as suspicious.
        0.004 = 0.4%, i.e. 40 occurrences in 10,000 utterances.
    min_absolute_count : int
        Floor so small datasets don't flag things on one or two hits.

    Returns
    -------
    The flagged strings, most frequent first.
    """
    normalised = utterances.fillna("").astype(str).str.strip()
    counts = normalised.value_counts()
    threshold = max(min_absolute_count, int(len(normalised) * min_repeat_ratio))

    flagged = []
    for text, count in counts.items():
        if count < threshold:
            break  # value_counts is sorted, so nothing below this qualifies
        if not text:
            continue
        if _HUMAN_SIGNALS.search(text):
            continue  # reads like something a person typed
        if not _looks_like_button(text):
            continue
        flagged.append(text)

    return flagged


def strip_menu_clicks(
    df: pd.DataFrame,
    text_col: str = "utterance",
    verbose: bool = True,
) -> tuple[pd.DataFrame, List[str]]:
    """
    Drop menu-click rows so clustering sees only typed messages.

    Returns the filtered dataframe and the list of labels that were removed,
    so the caller can report what was dropped rather than silently losing data.
    """
    labels = detect_menu_labels(df[text_col])
    if not labels:
        if verbose:
            print("  No menu-style labels detected — keeping all utterances.")
        return df, []

    label_set = set(labels)
    mask = df[text_col].fillna("").astype(str).str.strip().isin(label_set)
    removed = int(mask.sum())

    if verbose:
        print(f"  Removed {removed:,} menu clicks ({removed / max(len(df), 1) * 100:.1f}% of rows)")
        print(f"  Detected {len(labels)} menu labels, e.g.:")
        for label in labels[:8]:
            print(f"    • {label}")

    return df[~mask].copy(), labels


# ─────────────────────────────────────────────────────────────
# SYSTEM / AGENT MESSAGE REMOVAL
# ─────────────────────────────────────────────────────────────
#
# Preprocessing only drops turns whose speaker contains "(bot)". But a
# transcript also contains:
#
#   • system notices   "You are now chatting with Waynesha"
#                      "Waynesha has ended the chat"
#                      "Krystal King has joined the conversation"
#   • attachment lines "image001.png", "Attachment received"
#   • live agent turns — after escalation the agent speaks under a plain
#     name, so their messages look exactly like customer messages
#
# All of these get clustered as if a customer asked them, which is how you
# end up with a topic called "Attachment Handling" whose themes are
# "png, attachment, krystal king".

_SYSTEM_PATTERNS = [
    # Chat lifecycle
    r"\b(?:has|have)\s+(?:joined|left|ended|disconnected|reconnected)\b",
    r"\byou(?:'re| are)\s+now\s+chatting\s+with\b",
    r"\bchat\s+(?:session\s+)?(?:started|ended|closed|transferred|disconnected)\b",
    r"\b(?:is|are)\s+typing\b",
    r"\btransferr?(?:ed|ing)\s+(?:you\s+)?to\b",
    r"\bconnect(?:ed|ing)\s+you\s+(?:to|with)\b",
    r"\bplease\s+wait\s+while\s+(?:we|i)\s+(?:connect|transfer)\b",
    r"\bthank\s+you\s+for\s+contacting\b",
    r"\bagent\s+(?:has\s+)?(?:joined|left|ended)\b",
    r"\bconversation\s+(?:has\s+)?ended\b",
    # Attachments / uploads. Deliberately narrow: a customer writing
    # "can i send an attachment of the damage?" is a real question, so we
    # only match the notification forms, not any mention of the word.
    r"^\s*attachment\b.{0,30}$",
    r"\battachment\s+(?:received|added|uploaded|sent|shared|failed)\b",
    r"\b(?:received|uploaded|shared)\s+an?\s+attachment\b",
    r"\bfile\s+(?:upload|uploaded|received|sent|attached)\b",
    r"^\s*\S+\.(?:png|jpe?g|gif|pdf|docx?|xlsx?|heic|webp|zip)\s*$",
    r"\bimage\d+\.(?:png|jpe?g)\b",
    # Survey / rating prompts
    r"\brate\s+(?:your|this)\s+(?:experience|chat|conversation)\b",
    r"\bsurvey\b",
]

_SYSTEM_RE = re.compile("|".join(_SYSTEM_PATTERNS), re.IGNORECASE)


def strip_system_messages(
    df: pd.DataFrame,
    text_col: str = "utterance",
    verbose: bool = True,
) -> pd.DataFrame:
    """Drop chat-lifecycle notices, attachment lines and survey prompts."""
    mask = df[text_col].fillna("").astype(str).apply(lambda t: bool(_SYSTEM_RE.search(t)))
    removed = int(mask.sum())

    if verbose and removed:
        print(f"  Removed {removed:,} system/agent messages")
        for example in df.loc[mask, text_col].head(4):
            print(f"    • {str(example)[:70]}")

    return df[~mask].copy()


# ─────────────────────────────────────────────────────────────
# PERSON-NAME REMOVAL FROM THEMES
# ─────────────────────────────────────────────────────────────

def collect_speaker_names(transcripts: pd.Series) -> set[str]:
    """
    Pull every speaker name out of the raw transcript blobs.

    Lines look like "2026-08-17 11:59:19 Krystal King: Make Payment", so the
    text between the timestamp and the colon is a speaker. Collecting these
    gives us the customer names, agent names and bot names in this dataset —
    which are exactly the tokens that should never appear as a "theme".
    """
    speaker_re = re.compile(
        r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?\s+([^:\n]{1,60}?):",
    )

    names: set[str] = set()
    for blob in transcripts.fillna("").astype(str):
        for raw in speaker_re.findall(blob):
            cleaned = re.sub(r"\(bot\)", "", raw, flags=re.IGNORECASE).strip()
            for token in re.split(r"\s+", cleaned):
                token = re.sub(r"[^A-Za-z'-]", "", token).lower()
                if len(token) >= 2:
                    names.add(token)
    return names


def drop_name_themes(themes: List[str], names: set[str]) -> List[str]:
    """
    Remove themes that are just people's names.

    A theme is dropped if ANY word in it is a speaker name, so both
    "krystal king" and "chatting waynesha" go while "payment" stays. No
    legitimate theme should contain a person's name, so being aggressive
    here costs nothing.
    """
    stop = {"the", "a", "an", "and", "or", "of", "to", "for", "with", "is", "are"}
    kept = []
    for theme in themes:
        words = [w for w in re.split(r"\s+", theme.lower().strip()) if w and w not in stop]
        if not words:
            continue
        if any(re.sub(r"[^a-z'-]", "", w) in names for w in words):
            continue
        kept.append(theme)
    return kept


# ─────────────────────────────────────────────────────────────
# REPRESENTATIVE QUESTION SELECTION
# ─────────────────────────────────────────────────────────────

def _normalise_for_dedupe(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def _token_overlap(a: str, b: str) -> float:
    """Jaccard overlap on word sets — cheap near-duplicate check."""
    sa, sb = set(a.split()), set(b.split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def pick_representative_questions(
    texts: List[str],
    embeddings: Optional[np.ndarray] = None,
    k: int = 5,
    max_overlap: float = 0.6,
    min_words: int = 3,
) -> List[str]:
    """
    Pick up to k utterances that best represent what people actually asked.

    Strategy
    --------
    1. Drop anything too short to be a real question.
    2. Rank by closeness to the cluster centroid when embeddings are
       available — the centre of a cluster is, by construction, the most
       typical thing in it. Without embeddings, fall back to frequency.
    3. Walk the ranking and keep an utterance only if it isn't a near
       duplicate of one already chosen, so the reader gets several
       DIFFERENT questions rather than five ways of saying the same thing.
    4. Prefer utterances that end in a question mark, all else equal.
    """
    if not texts:
        return []

    cleaned = [t.strip() for t in texts if isinstance(t, str) and len(t.split()) >= min_words]
    if not cleaned:
        cleaned = [t.strip() for t in texts if isinstance(t, str) and t.strip()]
    if not cleaned:
        return []

    if embeddings is not None and len(embeddings) == len(texts):
        keep_idx = [
            i for i, t in enumerate(texts)
            if isinstance(t, str) and t.strip() in set(cleaned)
        ]
        if keep_idx:
            sub_emb = embeddings[keep_idx]
            centroid = sub_emb.mean(axis=0)
            norm = np.linalg.norm(centroid)
            if norm > 0:
                centroid = centroid / norm
            scores = sub_emb @ centroid
            order = np.argsort(-scores)
            ranked = [texts[keep_idx[i]].strip() for i in order]
        else:
            ranked = cleaned
    else:
        # No embeddings: most-repeated phrasings first, which are the
        # most typical ways of asking.
        freq = pd.Series(cleaned).value_counts()
        ranked = list(freq.index)

    # Slight preference for explicit questions, without overriding ranking.
    ranked.sort(key=lambda t: (0 if t.rstrip().endswith("?") else 1,))

    chosen: List[str] = []
    chosen_norm: List[str] = []

    for text in ranked:
        norm = _normalise_for_dedupe(text)
        if not norm:
            continue
        if any(_token_overlap(norm, existing) > max_overlap for existing in chosen_norm):
            continue
        chosen.append(text)
        chosen_norm.append(norm)
        if len(chosen) >= k:
            break

    return chosen