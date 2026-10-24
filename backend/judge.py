"""LLM-as-judge. One dimension per call — a single prompt asking for five
scores produces correlated numbers that look like signal and are not."""
import json

from eval_config import JUDGE_MODEL, RETRIEVAL_FLOOR
from llm_client import ask

COVERAGE_PROMPT = """You are evaluating whether a knowledge base article answers a customer's question.

CUSTOMER QUESTION:
{query}

RETRIEVED ARTICLE:
Title: {title}
Content: {content}

Decide whether a customer reading ONLY this article could resolve their question without contacting support.

Verdicts:
- "fully" — the article directly answers the question
- "partially" — related and useful, but part of the question is unanswered
- "not" — the article does not address the question

Judge the article as written. Do not credit it for information a reader would have to infer, or for being about the right general topic.

If the verdict is "partially" or "not", state what the article would need to say.

Return JSON only:
{{"verdict": "...", "reason": "<one sentence>", "missing": "<what it would need to say, or null>"}}"""

ROUTING_PROMPT = """A customer asked a question and the bot routed it to a conversational flow.

CUSTOMER QUESTION:
{query}

ROUTED TO FLOW: {flow_name}
FLOW PURPOSE: {flow_description}

Was this the right destination for this question?

Return JSON only:
{{"verdict": "correct" | "misrouted" | "no_flow_fits", "reason": "<one sentence>"}}"""


def _ask_json(prompt: str, names=None) -> dict:
    try:
        # Low reasoning effort: gpt-oss otherwise spends much of its output
        # budget (and the per-minute token limit) thinking before the JSON.
        raw = ask(prompt, model=JUDGE_MODEL, max_tokens=300, names=names,
                  reasoning_effort="low")
    except Exception as exc:  # noqa: BLE001 — one failed call must not sink a long run
        return {"verdict": "error", "reason": f"LLM call failed: {exc}"[:200]}
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    try:
        return json.loads(cleaned.strip())
    except json.JSONDecodeError:
        return {"verdict": "error", "reason": f"unparseable: {raw[:120]}"}


def judge_coverage(query, article, names=None):
    return _ask_json(COVERAGE_PROMPT.format(
        query=query, title=article["title"], content=article["content"]
    ), names=names)


def judge_routing(query, flow_name, flow_description, names=None):
    return _ask_json(ROUTING_PROMPT.format(
        query=query, flow_name=flow_name, flow_description=flow_description
    ), names=names)


def classify_failure(results, coverage_verdict, generated_ok=True):
    """Three failures look identical in a single score. Separate them.

    generated_ok is whether an answer generated from the article was
    usable. There is no generation step yet, so it defaults to True.
    A retrieval gap is not decided here — it needs the labelled set
    (see metrics.retrieval_gaps).
    """
    if coverage_verdict == "error":
        return "unjudged"           # judge failed; do not guess
    if not results or results[0]["score"] < RETRIEVAL_FLOOR:
        return "content_gap"        # nothing relevant exists
    if coverage_verdict == "not":
        return "content_gap"        # retrieved, but nothing answers it
    if coverage_verdict == "fully" and not generated_ok:
        return "clarity_gap"        # answer is there but unusable as written
    if coverage_verdict == "partially":
        return "clarity_gap"
    return "covered"
