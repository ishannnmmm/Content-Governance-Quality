interface LoadingStateProps {
  size?: number;
  className?: string;
}

export default function LoadingState({ size = 16, className = "" }: LoadingStateProps) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={`inline-block animate-spin rounded-full border-2 border-current border-t-transparent ${className}`}
      style={{ width: size, height: size }}
    />
  );
}
