import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, Info, Lock } from "lucide-react";
import type { UploadedFile } from "../types";
import FileUploader from "./FileUploader";
import FilePreview from "./FilePreview";
import LoadingState from "./LoadingState";

/**
 * Source options. Only "upload" is wired today — the CRM adapters attach
 * here later. Showing them disabled now sets the expectation that this is
 * a connected tool, not a file converter.
 */
const SOURCES = [
  { id: "upload", label: "Upload a file", ready: true },
  { id: "salesforce", label: "Salesforce", ready: false },
  { id: "egain", label: "eGain", ready: false },
  { id: "genesys", label: "Genesys", ready: false },
] as const;

type SourceId = (typeof SOURCES)[number]["id"];

interface WelcomeScreenProps {
  uploadedFile: UploadedFile | null;
  isUploading: boolean;
  onFileSelected: (file: File) => void;
  onReplaceFile: () => void;
  onAnalyze: () => void;
}

export default function WelcomeScreen({
  uploadedFile,
  isUploading,
  onFileSelected,
  onReplaceFile,
  onAnalyze,
}: WelcomeScreenProps) {
  const [source, setSource] = useState<SourceId>("upload");
  const [showFormats, setShowFormats] = useState(false);

  const selectedSource = SOURCES.find((s) => s.id === source)!;

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden px-6 py-16">
      <div className="pointer-events-none absolute -top-24 right-[-10%] h-72 w-72 rounded-full bg-brand-200/60 blur-3xl" />
      <div className="pointer-events-none absolute bottom-[-15%] left-[-10%] h-80 w-80 rounded-full bg-brand-300/40 blur-3xl" />

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: "easeOut" }}
        className="relative w-full max-w-xl"
      >
        <div className="mb-10 text-center">
          <h1 className="font-display text-4xl font-medium text-ink sm:text-5xl">ActionIQ</h1>
          <p className="mx-auto mt-3 max-w-sm text-base text-ink-muted">
            Let's turn your chat transcripts into actionable insights.
          </p>
        </div>

        <div className="rounded-[2rem] bg-white/70 p-2 shadow-soft backdrop-blur-sm">
          <div className="rounded-[1.75rem] bg-white p-6 sm:p-8">
            {/* ── Source selector ─────────────────────────────── */}
            <div className="mb-5">
              <div className="mb-2 flex items-center justify-between gap-3">
                <label htmlFor="source-select" className="text-sm text-ink-muted">
                  Where should we read from?
                </label>
                <button
                  type="button"
                  onClick={() => setShowFormats((v) => !v)}
                  aria-expanded={showFormats}
                  className="flex items-center gap-1 text-xs font-medium text-brand-600 transition-colors hover:text-brand-700"
                >
                  <Info className="h-3.5 w-3.5" strokeWidth={1.75} />
                  Accepted formats
                </button>
              </div>

              <select
                id="source-select"
                value={source}
                onChange={(e) => setSource(e.target.value as SourceId)}
                className="w-full rounded-xl border border-brand-200 bg-white px-3.5 py-2.5 text-sm text-ink transition-colors focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
              >
                {SOURCES.map((s) => (
                  <option key={s.id} value={s.id} disabled={!s.ready}>
                    {s.label}
                    {s.ready ? "" : " — coming soon"}
                  </option>
                ))}
              </select>

              <AnimatePresence initial={false}>
                {showFormats && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden"
                  >
                    <div className="mt-3 rounded-xl bg-brand-50 px-4 py-3 text-xs leading-relaxed text-ink-muted">
                      <p className="mb-1.5 font-medium text-brand-700">What to upload</p>
                      <p>
                        A CSV, JSON or TXT export of chat transcripts, one session per row, up to
                        50&nbsp;MB.
                      </p>
                      <p className="mt-2">
                        Required column <code className="text-brand-700">utterance</code> holding the
                        full transcript text. Include{" "}
                        <code className="text-brand-700">chatOfferAccepted</code> and the routed
                        intent where available — they let us measure escalation and routing accuracy.
                      </p>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* ── Upload area, or CRM placeholder ─────────────── */}
            {selectedSource.ready ? (
              uploadedFile ? (
                <FilePreview file={uploadedFile} onReplace={onReplaceFile} />
              ) : (
                <FileUploader onFileSelected={onFileSelected} isUploading={isUploading} />
              )
            ) : (
              <div className="rounded-3xl border border-dashed border-brand-200 bg-brand-50/50 px-6 py-10 text-center">
                <p className="text-sm font-medium text-ink">
                  {selectedSource.label} isn't connected yet
                </p>
                <p className="mt-1 text-sm text-ink-muted">
                  Pulling transcripts directly from {selectedSource.label} is on the way. For now,
                  export them and choose "Upload a file".
                </p>
              </div>
            )}
          </div>
        </div>

        {/* ── Data handling notice ──────────────────────────── */}
        <div className="mt-5 flex items-start gap-2.5 rounded-2xl bg-white/60 px-4 py-3">
          <Lock className="mt-0.5 h-4 w-4 shrink-0 text-ink-faint" strokeWidth={1.75} />
          <p className="text-xs leading-relaxed text-ink-muted">
            Names, email addresses, phone numbers and account numbers are removed before any
            analysis leaves your network.{" "}
            <a
              href="/data-handling"
              className="font-medium text-brand-600 underline underline-offset-2 transition-colors hover:text-brand-700"
            >
              How we handle your data
            </a>
          </p>
        </div>

        <div className="mt-6 flex justify-center">
          <button
            type="button"
            onClick={onAnalyze}
            disabled={!uploadedFile || isUploading || !selectedSource.ready}
            className="group flex items-center gap-2 rounded-full bg-brand-500 px-7 py-3.5 font-medium text-white shadow-card transition-all enabled:hover:bg-brand-600 enabled:hover:shadow-lg disabled:cursor-not-allowed disabled:opacity-40"
          >
            {isUploading ? (
              <>
                <LoadingState size={16} />
                Uploading…
              </>
            ) : (
              <>
                Analyze transcripts
                <ArrowRight className="h-4 w-4 transition-transform group-enabled:group-hover:translate-x-0.5" />
              </>
            )}
          </button>
        </div>
      </motion.div>
    </div>
  );
}
