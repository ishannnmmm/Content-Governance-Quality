import { CloudOff } from "lucide-react";

interface ErrorStateProps {
  message: string;
  onRetry: () => void;
}

export default function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div className="flex min-h-screen items-center justify-center px-6 py-16">
      <div className="w-full max-w-md rounded-[1.75rem] bg-white p-8 text-center shadow-soft">
        <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-full bg-blush-100">
          <CloudOff className="h-6 w-6 text-blush-600" strokeWidth={1.75} />
        </div>
        <h2 className="font-display text-2xl font-medium text-ink">Something didn't go through</h2>
        <p className="mt-2 text-sm text-ink-muted">{message}</p>
        <button
          type="button"
          onClick={onRetry}
          className="mt-6 rounded-full bg-blush-500 px-6 py-2.5 font-medium text-white transition-colors hover:bg-blush-600"
        >
          Try again
        </button>
      </div>
    </div>
  );
}
