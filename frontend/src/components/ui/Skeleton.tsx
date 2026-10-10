export function Skeleton({ className = '', lines = 3 }: { className?: string; lines?: number }) {
  return (
    <div className={`space-y-2 ${className}`} aria-hidden>
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="skeleton h-4" style={{ width: `${100 - (i % 3) * 18}%` }} />
      ))}
    </div>
  )
}

export function SkeletonCard({ rows = 4 }: { rows?: number }) {
  return (
    <div className="bg-surface border border-line rounded-md shadow-card p-5 space-y-3">
      <div className="skeleton h-5 w-1/3" />
      <Skeleton lines={rows} />
    </div>
  )
}