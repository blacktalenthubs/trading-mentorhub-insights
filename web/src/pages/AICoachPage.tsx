import { useState } from "react";
import {
  useAlertWinRates,
  useAckedWinRates,
  useFundamentals,
  useDailyAnalysis,
  useWeeklyAnalysis,
  useMTFContext,
} from "../api/hooks";
import { useCoachStream } from "../hooks/useCoachStream";
import { useFeatureGate } from "../hooks/useFeatureGate";
import ChatWindow from "../components/ai/ChatWindow";
import WinRateTable from "../components/ai/WinRateTable";
import FundamentalsCard from "../components/ai/FundamentalsCard";
import SetupAnalysisView from "../components/ai/SetupAnalysis";
import Card from "../components/ui/Card";

const TABS = [
  "Win Rates",
  "Fundamentals",
  "Daily",
  "Weekly",
  "MTF",
  "AI Coach",
  "Scanner",
] as const;

type Tab = (typeof TABS)[number];

export default function AICoachPage() {
  const { isPro } = useFeatureGate();

  if (!isPro) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-text-muted">AI Coach requires a Pro subscription.</p>
      </div>
    );
  }

  return <AICoachContent />;
}

function AICoachContent() {
  const [tab, setTab] = useState<Tab>("AI Coach");
  const [symbol, setSymbol] = useState("AAPL");

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="font-display text-2xl font-bold">AI Coach</h1>
        {/* Symbol input for analysis tabs */}
        {tab !== "Win Rates" && tab !== "AI Coach" && tab !== "Scanner" && (
          <input
            type="text"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            placeholder="Symbol"
            className="w-24 rounded border border-border-subtle bg-surface-3 px-2 py-1 text-sm text-text-primary focus:border-accent focus:outline-none"
          />
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 overflow-x-auto border-b border-border-subtle pb-1">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`whitespace-nowrap rounded-t px-3 py-1.5 text-xs font-medium transition-colors ${
              tab === t
                ? "bg-surface-3 text-text-primary"
                : "text-text-muted hover:text-text-secondary"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === "Win Rates" && <WinRatesTab />}
      {tab === "Fundamentals" && <FundamentalsTab symbol={symbol} />}
      {tab === "Daily" && <DailyTab symbol={symbol} />}
      {tab === "Weekly" && <WeeklyTab symbol={symbol} />}
      {tab === "MTF" && <MTFTab symbol={symbol} />}
      {tab === "AI Coach" && <CoachTab />}
      {tab === "Scanner" && <ScannerTab />}
    </div>
  );
}

function WinRatesTab() {
  const { data: alertRates } = useAlertWinRates();
  const { data: ackedRates } = useAckedWinRates();

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card title="Alert Win Rates">
        {alertRates && (
          <div className="space-y-4">
            <WinRateTable data={alertRates.overall} title="Overall" />
            <WinRateTable data={alertRates.by_symbol} title="By Symbol" />
            <WinRateTable data={alertRates.by_type} title="By Type" />
          </div>
        )}
      </Card>
      <Card title="Acked Trade Win Rates">
        {ackedRates && (
          <div className="space-y-4">
            <WinRateTable data={ackedRates.overall} title="Overall" />
            <WinRateTable data={ackedRates.by_symbol} title="By Symbol" />
          </div>
        )}
      </Card>
    </div>
  );
}

function FundamentalsTab({ symbol }: { symbol: string }) {
  const { data } = useFundamentals(symbol);
  return data ? <FundamentalsCard symbol={data.symbol} data={data.data} /> : null;
}

function DailyTab({ symbol }: { symbol: string }) {
  const { data } = useDailyAnalysis(symbol);
  return data ? (
    <SetupAnalysisView symbol={data.symbol} timeframe={data.timeframe} analysis={data.analysis} />
  ) : null;
}

function WeeklyTab({ symbol }: { symbol: string }) {
  const { data } = useWeeklyAnalysis(symbol);
  return data ? (
    <SetupAnalysisView symbol={data.symbol} timeframe={data.timeframe} analysis={data.analysis} />
  ) : null;
}

function MTFTab({ symbol }: { symbol: string }) {
  const { data } = useMTFContext(symbol);
  if (!data) return null;
  return (
    <div className="space-y-4">
      <SetupAnalysisView symbol={data.symbol} timeframe="Daily" analysis={data.daily} />
      <SetupAnalysisView symbol={data.symbol} timeframe="Weekly" analysis={data.weekly} />
      <SetupAnalysisView symbol={data.symbol} timeframe="Intraday" analysis={data.intraday} />
    </div>
  );
}

function CoachTab() {
  const { messages, streaming, sendMessage, stopStreaming, clearMessages } = useCoachStream();
  return (
    <ChatWindow
      messages={messages}
      streaming={streaming}
      onSend={sendMessage}
      onStop={stopStreaming}
      onClear={clearMessages}
    />
  );
}

function ScannerTab() {
  return (
    <Card title="Scanner Context">
      <p className="text-sm text-text-muted">
        Scanner context assembles watchlist analysis for AI review.
        Use the AI Coach tab to ask about specific setups.
      </p>
    </Card>
  );
}
