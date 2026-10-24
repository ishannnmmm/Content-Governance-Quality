import { useRef, useState } from "react";
import { UploadCloud } from "lucide-react";

const ACCEPTED_EXTENSIONS = [".csv", ".json", ".txt"];

interface FileUploaderProps {
  onFileSelected: (file: File) => void;
  isUploading: boolean;
}

function isAcceptedFile(file: File): boolean {
  const name = file.name.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => name.endsWith(ext));
}

export default function FileUploader({ onFileSelected, isUploading }: FileUploaderProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleFiles(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;

    if (!isAcceptedFile(file)) {
      setValidationError("That file type isn't supported yet. Please upload a CSV, JSON, or TXT file.");
      return;
    }

    setValidationError(null);
    onFileSelected(file);
  }

  return (
    <div>
      <label
        htmlFor="transcript-upload"
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragOver(true);
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragOver(false);
          handleFiles(e.dataTransfer.files);
        }}
        className={`group flex flex-col items-center justify-center gap-3 rounded-3xl border-2 border-dashed px-8 py-14 text-center transition-colors cursor-pointer
          ${
            isDragOver
              ? "border-blush-500 bg-blush-100"
              : "border-blush-300 bg-blush-100/60 hover:border-blush-400 hover:bg-blush-100"
          }`}
      >
        <div
          className={`flex h-14 w-14 items-center justify-center rounded-full bg-white shadow-soft transition-transform ${
            isDragOver ? "scale-110" : "group-hover:scale-105"
          }`}
        >
          <UploadCloud className="h-6 w-6 text-blush-600" strokeWidth={1.75} />
        </div>

        <div>
          <p className="font-medium text-ink">Upload chat transcripts</p>
          <p className="mt-1 text-sm text-ink-muted">
            Drag &amp; drop your file here, or{" "}
            <span className="font-medium text-blush-600 underline underline-offset-2">browse files</span>
          </p>
        </div>

        <p className="text-xs tracking-wide text-ink-faint">CSV &nbsp;•&nbsp; JSON &nbsp;•&nbsp; TXT</p>

        <input
          ref={inputRef}
          id="transcript-upload"
          type="file"
          accept={ACCEPTED_EXTENSIONS.join(",")}
          className="sr-only"
          disabled={isUploading}
          onChange={(e) => handleFiles(e.target.files)}
        />
      </label>

      {validationError && (
        <p className="mt-3 text-sm text-blush-700" role="alert">
          {validationError}
        </p>
      )}
    </div>
  );
}
