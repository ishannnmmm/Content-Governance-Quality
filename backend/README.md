# Chat Insights — backend

FastAPI server that runs the KB evaluation pipeline and serves its results
to the React frontend.

```
extract questions → deduplicate into canonical questions with counts
→ retrieve candidate articles → rerank → judge → classify failure
→ rank by frequency
```

The unit of analysis is a **customer question**, not a cluster. Each
distinct question gets a failure type, and the frontend groups by it:

| Failure type | Meaning | Goes to |
|---|---|---|
| `content_gap` | No article answers it | Article writers |
| `retrieval_gap` | The right article exists but wasn't in the top K (needs a labelled set) | Search config owners |
| `clarity_gap` | An article partly answers it | Authors of that article |
| `covered` | An article fully answers it | — |

## Modules

| File | Purpose |
|---|---|
| `diagnose_kb.py` | Step 0 sanity check of the KB and bot-flow files. Run it first |
| `llm_client.py` | The **only** module that calls Groq. Scrubs PII on every call |
| `retrieval.py` | `KBIndex` — dense + BM25, fused with RRF, reranked by a cross-encoder |
| `judge.py` | Coverage and routing verdicts (one dimension per call), failure classification |
| `canonical.py` | Deduplication into canonical questions (agglomerative, distance cutoff) |
| `metrics.py` | Recall@K, MRR, judge-agreement checks, per-run aggregates |
| `eval_config.py` | Tuning constants and column mappings, all overridable by env var |
| `improved_coverage_analysis.py` | Stage 2: group → index → retrieve → judge → classify |
| `improved_utterance_analysis.py` | Question loading and embedding (`.npy` cache); k-means kept only as optional navigation grouping |
| `preprocess_transcripts.py` | Extracts customer turns, keeps bot replies in `bot_response`, carries `outcome` / `routed_intent` through |
| `api_server.py` | HTTP API and job orchestration |
| `run_full_pipeline.py` | The same pipeline from the command line |

## Order of work

1. **Diagnose the KB.** Do not move on until the probe returns titles a
   person would agree are relevant.
   ```bash
   python diagnose_kb.py /path/to/kb_articles.csv /path/to/bot_flows_tgr.csv
   ```
   If your KB headers aren't `article_id` / `title` / `content`, set
   `KB_ID_COL` / `KB_TITLE_COL` / `KB_TEXT_COL`.
2. **Measure retrieval** on 50–100 questions you write from article titles
   (`question`, `relevant_article_ids` — semicolon-separated).
   Gate: Recall@5 above 0.8.
   ```bash
   python metrics.py retrieval /path/to/kb_articles.csv labelled_questions.csv
   ```
3. **Validate the judge** against two CX reviewers on ~100 query-article
   pairs, including known negatives (`reviewer_a`, `reviewer_b`, `judge`).
   Gate: judge agreement near human agreement. Re-run after any prompt edit.
   ```bash
   python metrics.py agreement labels.csv
   ```

## Running

```bash
pip install -r requirements.txt
# put your key and file paths in run_server.sh — it is gitignored
./run_server.sh                 # → http://localhost:8001
```

`GROQ_API_KEY` is required — coverage is decided by the judge, so jobs
fail at validation without it. Optional: `LABELLED_SET_FILE` points at the
labelled questions from step 2 and enables retrieval-gap detection; without
it the UI shows retrieval gaps as "not measured".

Then, in another terminal:

```bash
cd ../frontend
npm install
npm run dev                     # → http://localhost:5173
```

Check everything is wired up before uploading anything:

```bash
curl http://localhost:8001/api/health
```

## Tuning

All in `eval_config.py`, each overridable by an env var of the same name:
`RETRIEVAL_FLOOR` (starts at 0.0 — set it from observed cross-encoder
scores on known-good and known-bad pairs), `RRF_K`, `CANDIDATES`, `TOP_K`,
`JUDGE_TOP_K` (articles judged per question, default 3), `DEDUPE_THRESHOLD`,
`JUDGE_MODEL`, `JUDGE_CONCURRENCY`. Questions whose best article scores
below `RETRIEVAL_FLOOR` are not sent to the judge at all.

`GROQ_RPM` / `GROQ_TPM` (in `llm_client.py`, defaults 30 / 8000) pace LLM
calls to your Groq tier. Run time is bounded by these: at 8K tokens a
minute the judge manages roughly 6 calls a minute.

## Endpoints

| Method | Path | Maps to frontend call |
|---|---|---|
| POST | `/api/transcripts` | `uploadTranscript(file)` |
| POST | `/api/jobs` | `startPipeline(fileId)` |
| GET | `/api/jobs/{id}/status` | `getPipelineStatus(jobId)` |
| GET | `/api/jobs/{id}/results` | `getAnalysisResults(jobId)` |
| GET | `/api/health` | — (setup check) |

Jobs run on a background thread; the frontend polls `/status`. Progress
comes from real step completion, weighted by cost — judging is 35% of the
bar because it is one LLM call per question-article pair, and its label
shows `done/total` while it runs.

## Privacy

Every LLM prompt passes through `pii_scrubber.scrub()` inside
`llm_client.ask()`, with the speaker names from the transcripts as a
case-insensitive denylist. Customer text in the payload is scrubbed the
same way in `build_frontend_payload()`. Speaker names that are also words
in the KB (e.g. "Bill") are exempt from the denylist so billing questions
stay intact; "First Last" names are still caught by pattern.

Regex scrubbing has gaps — scrub a sample and read it before any batch
goes out. For production data consider Microsoft Presidio.

**Jobs are in-memory.** Restarting the server loses job state (output
files on disk survive).
