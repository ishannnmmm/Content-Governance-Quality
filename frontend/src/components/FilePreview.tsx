import { CheckCircle2, RotateCcw } from "lucide-react";
import type { UploadedFile } from "../types";
import { formatBytes } from "../utils/format";

interface FilePreviewProps {
  file: UploadedFile;
  onReplace: () => void;
}

export default function FilePreview({ file, onReplace }: FilePreviewProps) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-3xl border border-blush-200 bg-white px-6 py-5 shadow-soft">
      <div className="flex min-w-0 items-center gap-3">
        <CheckCircle2 className="h-5 w-5 shrink-0 text-sage-500" strokeWidth={1.75} />
        <div className="min-w-0">
          <p className="truncate font-medium text-ink">{file.name}</p>
          <p className="text-sm text-ink-muted">{formatBytes(file.size)}</p>
        </div>
      </div>

      <button
        type="button"
        onClick={onReplace}
        className="flex shrink-0 items-center gap-1.5 rounded-full border border-blush-200 px-3.5 py-1.5 text-sm font-medium text-ink-muted transition-colors hover:border-blush-400 hover:text-ink"
      >
        <RotateCcw className="h-3.5 w-3.5" strokeWidth={1.75} />
        Replace file
      </button>
    </div>
  );
}
