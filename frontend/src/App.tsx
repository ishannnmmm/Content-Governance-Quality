import { useCallback, useEffect, useRef, useState } from "react";
import { getAnalysisResults, getPipelineStatus, startPipeline, uploadTranscript } from "./api/backend";
import type { AnalysisResult, AppStage, PipelineStatus, UploadedFile } from "./types";
import WelcomeScreen from "./components/WelcomeScreen";
import PipelineProgress from "./components/PipelineProgress";
import ResultsDashboard from "./components/ResultsDashboard";
import ErrorState from "./components/ErrorState";

// Real pipeline runs take minutes, so poll gently. Step transitions are
// what the user watches, and those change far slower than twice a second.
const POLL_INTERVAL_MS = 1500;

export default function App() {
  const [stage, setStage] = useState<AppStage>("welcome");
  const [uploadedFile, setUploadedFile] = useState<UploadedFile | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const pollRef = useRef<number | null>(null);

  const clearPolling = useCallback(() => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => clearPolling, [clearPolling]);

  async function handleFileSelected(file: File) {
    setIsUploading(true);
    setErrorMessage(null);
    try {
      const uploaded = await uploadTranscript(file);
      setUploadedFile(uploaded);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "The upload didn't go through. Please try again.");
    } finally {
      setIsUploading(false);
    }
  }

  function handleReplaceFile() {
    setUploadedFile(null);
  }

  async function handleAnalyze() {
    if (!uploadedFile) return;
    setErrorMessage(null);

    try {
      const { jobId: newJobId } = await startPipeline(uploadedFile.id);
      setStage("processing");
      beginPolling(newJobId);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Couldn't start the analysis. Please try again.");
      setStage("error");
    }
  }

  function beginPolling(id: string) {
    clearPolling();

    async function poll() {
      try {
        const status = await getPipelineStatus(id);
        setPipelineStatus(status);

        if (status.state === "completed") {
          clearPolling();
          const analysis = await getAnalysisResults(id);
          setResult(analysis);
          setStage("results");
        } else if (status.state === "failed") {
          clearPolling();
          setErrorMessage(status.error ?? "The analysis couldn't be completed. Please try again.");
          setStage("error");
        }
      } catch (err) {
        clearPolling();
        setErrorMessage(err instanceof Error ? err.message : "Lost connection to the analysis job.");
        setStage("error");
      }
    }

    poll();
    pollRef.current = window.setInterval(poll, POLL_INTERVAL_MS);
  }

  function handleRetry() {
    clearPolling();
    setStage("welcome");
    setUploadedFile(null);
    setPipelineStatus(null);
    setResult(null);
    setErrorMessage(null);
  }

  if (stage === "processing" && pipelineStatus) {
    return <PipelineProgress status={pipelineStatus} />;
  }

  if (stage === "results" && result) {
    return <ResultsDashboard result={result} />;
  }

  if (stage === "error") {
    return <ErrorState message={errorMessage ?? "Something went wrong."} onRetry={handleRetry} />;
  }

  return (
    <WelcomeScreen
      uploadedFile={uploadedFile}
      isUploading={isUploading}
      onFileSelected={handleFileSelected}
      onReplaceFile={handleReplaceFile}
      onAnalyze={handleAnalyze}
    />
  );
}
