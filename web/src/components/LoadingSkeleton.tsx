/** Reusable loading skeleton components. */

export function SkeletonCard() {
  return (
    <div className="animate-pulse rounded-lg bg-gray-900 p-4">
      <div className="mb-2 h-3 w-20 rounded bg-gray-800" />
      <div className="h-6 w-24 rounded bg-gray-800" />
    </div>
  );
}

export function SkeletonRow() {
  return (
    <div className="flex animate-pulse gap-4 border-t border-gray-800 py-3">
      <div className="h-4 w-16 rounded bg-gray-800" />
      <div className="h-4 w-24 rounded bg-gray-800" />
      <div className="h-4 w-20 rounded bg-gray-800" />
      <div className="h-4 w-16 rounded bg-gray-800" />
    </div>
  );
}

export function SkeletonTable({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-0">
      {Array.from({ length: rows }).map((_, i) => (
        <SkeletonRow key={i} />
      ))}
    </div>
  );
}

export function SkeletonGrid({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}

export function PageLoading() {
  return (
    <div className="flex h-32 items-center justify-center">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-gray-700 border-t-blue-500" />
    </div>
  );
}
