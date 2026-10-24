interface SummaryCardProps {
  label: string;
  value: string | number;
}

export default function SummaryCard({ label, value }: SummaryCardProps) {
  return (
    <div className="rounded-2xl border border-blush-200/70 bg-white/70 px-5 py-4">
      <p className="text-sm text-ink-muted">{label}</p>
      <p className="mt-1 font-display text-2xl font-medium text-ink">{value}</p>
    </div>
  );
}
