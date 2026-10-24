#!/usr/bin/env python3
"""
agentic_analyzer.py
━━━━━━━━━━━━━━━━━━━
The AI analysis layer. Reads all pipeline outputs (local files),
scrubs PII from any sample utterances, then sends structured analysis
prompts to the Groq API to generate actionable business intelligence.

What touches the LLM (Groq API):
  • Aggregated cluster metrics (no PII — just numbers)
  • PII-scrubbed sample utterances (names/emails/phones/accounts redacted)
  • KB article titles and bot-flow intent names (not PII)
  • Coverage scores and gap rankings (just numbers)

What NEVER touches the LLM:
  • Raw customer transcripts
  • Customer names, emails, phone numbers, policy numbers
  • Full utterance datasets
  • Embedding matrices

Architecture:
  Local files → Read & aggregate → PII-scrub samples →
  Groq API (analysis prompts) → Executive report (local .md file)

Usage:
    export GROQ_API_KEY="gsk_..."
    python agentic_analyzer.py

    Or after running the full pipeline:
    python agentic_analyzer.py --output-dir pipeline_output

Requirements:
    pip install groq pandas numpy
"""

import os
import sys
import json
import argparse
import pandas as pd
import numpy as np

# ─────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────

DEFAULT_OUTPUT_DIR = "pipeline_output"
MODEL = "openai/gpt-oss-120b"
MAX_TOKENS = 4096

# ─────────────────────────────────────────────────────────────
# LLM CLIENT
# ─────────────────────────────────────────────────────────────

def get_client():
    """Fail fast if no API key. The client itself lives in llm_client."""
    if not os.environ.get("GROQ_API_KEY", ""):
        print("❌  GROQ_API_KEY not set.")
        print("    export GROQ_API_KEY=\"gsk_...\"")
        print()
        print("    Get a key at: https://console.groq.com/keys")
        sys.exit(1)
    return None


def ask_llm(client, system_prompt: str, user_prompt: str) -> str:
    """Send a single prompt through llm_client, which scrubs it first."""
    from llm_client import ask

    return ask(user_prompt, system=system_prompt, model=MODEL, max_tokens=MAX_TOKENS)


# ─────────────────────────────────────────────────────────────
# DATA LOADING
# ─────────────────────────────────────────────────────────────

def load_pipeline_outputs(output_dir: str) -> dict:
    """Load all CSVs produced by the pipeline into a dict of DataFrames."""
    files = {
        "utterances":       "customer_utterances.csv",
        "clustered":        "utterances_clustered.csv",
        "cluster_summary":  "cluster_summary.csv",
        "coverage":         "utterance_level_coverage.csv",
        "coverage_summary": "cluster_coverage_summary.csv",
        "gap_report":       "gap_report_prioritised.csv",
    }

    data = {}
    for key, filename in files.items():
        path = os.path.join(output_dir, filename)
        if os.path.exists(path):
            data[key] = pd.read_csv(path, encoding="utf-8-sig")
            print(f"  ✓ {filename} ({len(data[key]):,} rows)")
        else:
            print(f"  ⚠ {filename} not found — skipping")
            data[key] = None

    return data


# ─────────────────────────────────────────────────────────────
# PII-SAFE SAMPLE EXTRACTION
# ─────────────────────────────────────────────────────────────

def get_scrubbed_samples(df: pd.DataFrame, text_col: str,
                         group_col: str, n_per_group: int = 5) -> dict:
    """
    For each group, pull n sample utterances and scrub PII.
    Returns {group_id: [scrubbed_utterance, ...]}.
    """
    from pii_scrubber import scrub

    samples = {}
    for gid, grp in df.groupby(group_col):
        raw = grp[text_col].dropna().sample(
            min(n_per_group, len(grp)), random_state=42
        ).tolist()
        samples[gid] = [scrub(u) for u in raw]
    return samples


# ─────────────────────────────────────────────────────────────
# ANALYSIS AGENTS
# ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior customer experience analyst examining 
chatbot and customer support data for an insurance company. 

You are working with pre-processed, aggregated data. Any customer utterance 
samples you see have already been PII-scrubbed (names replaced with 
[CUSTOMER], emails with [EMAIL], etc.).

Your role:
- Identify patterns in what customers are asking about most
- Assess whether the existing knowledge base and bot flows address those needs
- Distinguish between similarity-based coverage (semantic match exists) and 
  confirmed resolution (which this data cannot establish)
- Provide actionable, specific recommendations
- Be precise about what the data shows vs. what it cannot prove

Never invent customer quotes, KB articles, or statistics not in the data."""


def analyze_top_queries(client, data: dict) -> str:
    """Agent 1: What are customers saying most?"""
    print("\n🔍  Agent 1: Analyzing top customer queries...")

    cs = data["cluster_summary"]
    if cs is None:
        return "Cluster summary not available."

    # Build context from cluster summary
    cluster_info = cs.sort_values("volume" if "volume" in cs.columns
                                  else "total_utterances", ascending=False)

    # Get scrubbed samples if we have the clustered data
    samples = {}
    if data["clustered"] is not None:
        samples = get_scrubbed_samples(
            data["clustered"], "clean_text", "cluster", n_per_group=8
        )

    # Build the prompt with real data
    cluster_blocks = []
    for _, row in cluster_info.iterrows():
        cid = row.get("cluster", row.get("cluster_id", "?"))
        name = row.get("cluster_name", f"Cluster {cid}")
        vol = row.get("volume", row.get("total_utterances", 0))
        esc = row.get("escalation_rate", 0)
        sent = row.get("avg_sentiment", 0)
        frust = row.get("frustration_index", 0)

        block = f"""### Cluster {cid}: {name}
- Volume: {vol:,} utterances
- Escalation rate: {esc:.1%}
- Avg sentiment: {sent:.3f}
- Frustration index: {frust:.4f}"""

        themes = row.get("top_themes", "")
        if themes and str(themes) != "nan":
            block += f"\n- TF-IDF themes: {themes}"

        if cid in samples:
            block += "\n- Sample utterances (PII-scrubbed):"
            for s in samples[cid]:
                block += f"\n    • \"{s}\""

        cluster_blocks.append(block)

    prompt = f"""Here are the customer utterance clusters from our chatbot analysis, 
sorted by volume. Each cluster groups semantically similar customer messages.

{chr(10).join(cluster_blocks)}

Based on this data:

1. What are the top 5 most common things customers are asking about? 
   For each, cite the cluster(s), volume, and representative utterances.

2. Are any clusters describing the same customer need under different labels? 
   If so, which ones and why do you think so?

3. Which clusters have the highest frustration indicators (escalation + negative sentiment)?
   What does this suggest about those customer needs?

4. Are there any patterns in what drives escalation vs. what gets handled by the bot?

Be specific — reference actual cluster names, volumes, and sample utterances."""

    return ask_llm(client, SYSTEM_PROMPT, prompt)


def analyze_coverage(client, data: dict) -> str:
    """Agent 2: How well does the KB + bot cover customer needs?"""
    print("🔍  Agent 2: Analyzing knowledge coverage...")

    cov = data["coverage_summary"]
    gap = data["gap_report"]
    if cov is None:
        return "Coverage summary not available."

    # Build coverage context
    cov_blocks = []
    for _, row in cov.iterrows():
        cid = row.get("cluster_id", row.get("cluster", "?"))
        name = row.get("cluster_name", f"Cluster {cid}")
        block = f"""### {name} (Cluster {cid})
- Total utterances: {row.get('total_utterances', 0):,}
- Fully covered: {row.get('pct_fully_covered', 0)}%
- Partially covered: {row.get('pct_partial_covered', 0)}%
- Not covered: {row.get('pct_not_covered', 0)}%
- Avg similarity score: {row.get('avg_similarity', 0):.3f}
- Escalation rate: {row.get('escalation_rate', 0):.1%}"""
        cov_blocks.append(block)

    # Gap report context
    gap_blocks = []
    if gap is not None:
        for _, row in gap.head(10).iterrows():
            block = f"""- {row.get('severity', '?')} | {row.get('cluster_name', '?')} | 
  Gap score: {row.get('gap_priority_score', 0):.4f} | 
  {row.get('pct_not_covered', 0)}% not covered | 
  Escalation: {row.get('escalation_rate', 0):.1%} | 
  Themes: {row.get('top_themes', 'N/A')}"""
            gap_blocks.append(block)

    prompt = f"""Here is the coverage analysis showing how well existing KB articles 
and bot flows semantically match customer utterances.

IMPORTANT CONTEXT: "Coverage" here means semantic similarity between customer 
utterances and KB/bot-flow text. A high similarity score means the text is 
semantically close — it does NOT prove the customer actually received that 
article or that the bot triggered that intent. Keep this distinction clear.

## Coverage by Cluster
{chr(10).join(cov_blocks)}

## Top Gaps (ranked by gap_priority_score = %_not_covered × escalation_rate × log(volume))
{chr(10).join(gap_blocks) if gap_blocks else 'No gap report available.'}

Based on this data:

1. Which customer needs appear well-addressed by existing KB/bot content? 
   (high similarity + low escalation)

2. Which have the most significant potential coverage gaps? 
   (low similarity + high volume + high escalation)

3. Are there clusters with high similarity but high escalation? 
   What might explain that pattern?

4. Are there clusters with low similarity but low escalation? 
   What might explain that?

5. For the top 3 gaps, what specific KB content or bot-flow improvements 
   would you recommend investigating?

Be precise about what this data can and cannot establish."""

    return ask_llm(client, SYSTEM_PROMPT, prompt)


def generate_executive_summary(client, data: dict,
                               query_analysis: str,
                               coverage_analysis: str) -> str:
    """Agent 3: Synthesize everything into an executive summary."""
    print("🔍  Agent 3: Generating executive summary...")

    # Calculate high-level stats
    stats = {}
    if data["utterances"] is not None:
        stats["total_utterances"] = len(data["utterances"])
    if data["cluster_summary"] is not None:
        cs = data["cluster_summary"]
        stats["num_clusters"] = len(cs)
        vol_col = "volume" if "volume" in cs.columns else "total_utterances"
        if vol_col in cs.columns:
            stats["largest_cluster"] = cs.loc[cs[vol_col].idxmax(), "cluster_name"]
            stats["largest_volume"] = int(cs[vol_col].max())
    if data["coverage_summary"] is not None:
        cov = data["coverage_summary"]
        total = cov["total_utterances"].sum() if "total_utterances" in cov.columns else 0
        if total > 0 and "pct_not_covered" in cov.columns:
            weighted_not_covered = (
                cov["pct_not_covered"] * cov["total_utterances"]
            ).sum() / total
            stats["overall_not_covered_pct"] = round(weighted_not_covered, 1)
    if data["gap_report"] is not None:
        stats["critical_gaps"] = len(
            data["gap_report"][data["gap_report"]["severity"].str.contains("CRITICAL", na=False)]
        )

    prompt = f"""You have completed a customer conversation intelligence analysis. 
Here are the results from two analysis passes:

## HIGH-LEVEL STATISTICS
{json.dumps(stats, indent=2)}

## ANALYSIS 1: What Customers Are Saying
{query_analysis}

## ANALYSIS 2: Knowledge Coverage Assessment
{coverage_analysis}

Write an executive summary (2-3 pages) structured as:

1. **Overview** — What was analyzed, scale of data, methodology note 
   (similarity-based coverage, not verified resolution)

2. **Key Findings** — Top 3-5 findings, each with:
   - The finding (one sentence)
   - Supporting evidence from the data
   - Business impact

3. **Coverage Assessment** — Overall health of KB + bot flows, 
   where they're strong, where gaps exist

4. **Priority Recommendations** — Top 5 specific, actionable items, 
   ranked by potential impact. For each: what to do, why, expected effect.

5. **Limitations & Next Steps** — What this analysis cannot establish 
   and what additional data would help

Keep it concrete and data-driven. Reference specific clusters, volumes, 
and scores. Avoid generic advice."""

    return ask_llm(client, SYSTEM_PROMPT, prompt)


def offer_followup(client, data: dict, report_text: str):
    """Agent 4: Interactive follow-up — ask questions about the results."""
    print("\n" + "═" * 60)
    print("  💬  FOLLOW-UP MODE — Ask questions about the analysis")
    print("      Type 'quit' or 'exit' to stop.")
    print("═" * 60)

    conversation = [
        {"role": "user", "content": f"Here is the executive summary of our analysis:\n\n{report_text}"},
        {"role": "assistant", "content": "I've reviewed the full analysis. What would you like to explore further?"},
    ]

    while True:
        try:
            question = input("\n  You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not question or question.lower() in ("quit", "exit", "q"):
            print("\n  Done. Full report saved to your output directory.")
            break

        conversation.append({"role": "user", "content": question})

        try:
            response = client.chat.completions.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                messages=[{"role": "system", "content": SYSTEM_PROMPT}] + conversation,
            )
            answer = response.choices[0].message.content
            conversation.append({"role": "assistant", "content": answer})
            print(f"\n  Groq: {answer}")
        except Exception as e:
            print(f"\n  ⚠️  Error: {e}")
            conversation.pop()  # remove failed question


# ─────────────────────────────────────────────────────────────
# REPORT WRITER
# ─────────────────────────────────────────────────────────────

def write_report(output_dir: str, sections: dict):
    """Write the full analysis report as a Markdown file."""
    path = os.path.join(output_dir, "executive_report.md")

    with open(path, "w") as f:
        f.write("# Customer Conversation Intelligence Report\n\n")
        f.write("---\n\n")

        if "executive_summary" in sections:
            f.write("## Executive Summary\n\n")
            f.write(sections["executive_summary"])
            f.write("\n\n---\n\n")

        if "top_queries" in sections:
            f.write("## Detailed Analysis: Customer Query Patterns\n\n")
            f.write(sections["top_queries"])
            f.write("\n\n---\n\n")

        if "coverage" in sections:
            f.write("## Detailed Analysis: Knowledge Coverage\n\n")
            f.write(sections["coverage"])
            f.write("\n\n---\n\n")

        f.write("## Methodology Note\n\n")
        f.write("This analysis uses semantic similarity (cosine similarity of ")
        f.write("sentence-transformer embeddings) to estimate coverage. ")
        f.write("A high similarity score means the customer utterance is ")
        f.write("textually close to an existing KB article or bot-flow training ")
        f.write("phrase. It does **not** confirm that the customer was shown ")
        f.write("that article, that the bot intent was triggered, or that the ")
        f.write("query was successfully resolved. Escalation rates reflect ")
        f.write("whether customers accepted a handoff to a human agent, which ")
        f.write("can occur for policy reasons as well as bot limitations.\n")

    print(f"\n📄  Executive report → {path}")
    return path


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="AI-powered analysis of pipeline outputs"
    )
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR,
                        help="Directory containing pipeline output CSVs")
    parser.add_argument("--no-interactive", action="store_true",
                        help="Skip interactive follow-up mode")
    args = parser.parse_args()

    print("=" * 60)
    print("  🤖  AGENTIC ANALYZER — AI-Powered Insights")
    print("=" * 60)

    # 1. Init client
    client = get_client()
    print("  ✓ Groq API key found\n")

    # 2. Load pipeline outputs
    print("📂  Loading pipeline outputs...")
    data = load_pipeline_outputs(args.output_dir)

    # 3. Run analysis agents
    sections = {}

    sections["top_queries"] = analyze_top_queries(client, data)
    print("  ✓ Query analysis complete")

    sections["coverage"] = analyze_coverage(client, data)
    print("  ✓ Coverage analysis complete")

    sections["executive_summary"] = generate_executive_summary(
        client, data, sections["top_queries"], sections["coverage"]
    )
    print("  ✓ Executive summary generated")

    # 4. Write report
    report_path = write_report(args.output_dir, sections)

    # 5. Print summary
    print("\n" + "=" * 60)
    print("  ✅  Analysis complete!")
    print("=" * 60)
    print(f"\n  📄  Executive report:  {report_path}")
    print(f"  📊  Dashboard:         {os.path.join(args.output_dir, 'coverage_dashboard.html')}")
    print(f"  📋  Gap report:        {os.path.join(args.output_dir, 'gap_report_prioritised.csv')}")

    # 6. Interactive follow-up
    if not args.no_interactive:
        offer_followup(client, data, sections["executive_summary"])


if __name__ == "__main__":
    main()