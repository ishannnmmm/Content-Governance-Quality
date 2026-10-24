import type { AnalysisResult, PipelineStatus, UploadedFile } from "../types";

/**
 * ─────────────────────────────────────────────────────────────
 * BACKEND CLIENT
 * ─────────────────────────────────────────────────────────────
 * Talks to the FastAPI server in ../backend/api_server.py.
 *
 * In development, vite.config.ts proxies /api to http://localhost:8000,
 * so no base URL or CORS handling is needed here. In production, set
 * VITE_API_BASE_URL if the API lives on a different origin.
 * ─────────────────────────────────────────────────────────────
 */

const BASE = import.meta.env.VITE_API_BASE_URL ?? "";

/** Pull the server's error message out of a failed response. */
async function readError(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail) && body.detail[0]?.msg) return body.detail[0].msg;
  } catch {
    // response wasn't JSON — fall through
  }
  return fallback;
}

export async function uploadTranscript(file: File): Promise<UploadedFile> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${BASE}/api/transcripts`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    throw new Error(await readError(res, "The upload didn't go through. Please try again."));
  }
  return res.json();
}

export async function startPipeline(fileId: string): Promise<{ jobId: string }> {
  const res = await fetch(`${BASE}/api/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fileId }),
  });

  if (!res.ok) {
    throw new Error(await readError(res, "Couldn't start the analysis. Please try again."));
  }
  return res.json();
}

export async function getPipelineStatus(jobId: string): Promise<PipelineStatus> {
  const res = await fetch(`${BASE}/api/jobs/${jobId}/status`);

  if (!res.ok) {
    throw new Error(await readError(res, "Lost track of this analysis job."));
  }
  return res.json();
}

export async function getAnalysisResults(jobId: string): Promise<AnalysisResult> {
  const res = await fetch(`${BASE}/api/jobs/${jobId}/results`);

  if (!res.ok) {
    throw new Error(await readError(res, "Couldn't load the analysis results."));
  }
  return res.json();
}
