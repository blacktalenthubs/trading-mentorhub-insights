import { useScanner } from "../api/hooks";
import WatchlistEditor from "../components/WatchlistEditor";
import SignalCard from "../components/SignalCard";

export default function ScannerPage() {
  const { data: signals, isLoading, refetch, isFetching } = useScanner();

  const potentialEntryCount = signals?.filter(
    (s) => s.action_label === "Potential Entry"
  ).length ?? 0;
  const avgScore = signals && signals.length > 0
    ? Math.round(signals.reduce((sum, s) => sum + (s.score ?? 0), 0) / signals.length)
    : 0;
  const topGradeCount = signals?.filter(
    (s) => s.grade === "A+" || s.grade === "A"
  ).length ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Scanner</h1>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="rounded bg-gray-800 px-3 py-1.5 text-sm hover:bg-gray-700 disabled:opacity-50"
        >
          {isFetching ? "Scanning..." : "Refresh"}
        </button>
      </div>

      <WatchlistEditor />

      {/* KPI Summary Row */}
      {signals && signals.length > 0 && (
        <div className="grid grid-cols-4 gap-3">
          <div className="rounded-lg bg-gray-900 p-3 text-center">
            <p className="text-xs text-gray-500">SCANNED</p>
            <p className="text-2xl font-bold text-gray-300">{signals.length}</p>
          </div>
          <div className="rounded-lg bg-gray-900 p-3 text-center">
            <p className="text-xs text-gray-500">POTENTIAL ENTRIES</p>
            <p className="text-2xl font-bold text-green-400">{potentialEntryCount}</p>
          </div>
          <div className="rounded-lg bg-gray-900 p-3 text-center">
            <p className="text-xs text-gray-500">AVG SCORE</p>
            <p className="text-2xl font-bold text-blue-400">{avgScore}</p>
          </div>
          <div className="rounded-lg bg-gray-900 p-3 text-center">
            <p className="text-xs text-gray-500">A+ / A</p>
            <p className="text-2xl font-bold text-blue-400">{topGradeCount}</p>
          </div>
        </div>
      )}

      {isLoading && <p className="text-sm text-gray-500">Loading scanner results...</p>}

      {signals && signals.length > 0 && (
        <div className="space-y-3">
          {signals.map((s) => (
            <SignalCard key={s.symbol} signal={s} />
          ))}
        </div>
      )}

      {signals && signals.length === 0 && !isLoading && (
        <p className="text-sm text-gray-500">No signals. Add symbols to your watchlist above.</p>
      )}
    </div>
  );
}
