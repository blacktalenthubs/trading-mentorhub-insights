/** TanStack Query hooks for all API endpoints. */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import { toast } from "../components/Toast";
import type { InPlaySnapshot, SwingSnapshot, SwingRun, ConvictionSnapshot, ConvictionRun, WeeklyStageSnapshot } from "../pages/InPlay.types";
import type {
  AuthTokens, SignalResult, Alert, User,
  OptionsTrade, OptionsTradeStats, EquityPoint,
  SpyRegime, SwingTrade, ScorecardItem,
  WinRateData, SetupAnalysis, MTFContext, NotificationPrefs,
  NotificationRouting,
  PerformanceBreakdown,
} from "../types";

// --- In-Play Volume Screener (spec 62) ---

export function useInPlay(preset: string, hasSetup: boolean) {
  return useQuery({
    queryKey: ["in-play", preset, hasSetup],
    queryFn: () =>
      api.get<InPlaySnapshot>(
        `/screener/in-play?preset=${encodeURIComponent(preset)}&has_setup=${hasSetup}`,
      ),
    // Refresh roughly with the server's ~10-min cadence; the snapshot is cached server-side.
    refetchInterval: 60_000,
  });
}

export function useRefreshInPlay() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post("/screener/in-play/refresh", {}),
    onSuccess: () => {
      toast.info("In-play scan started — refreshing in a few seconds");
      setTimeout(() => qc.invalidateQueries({ queryKey: ["in-play"] }), 12000);
    },
    onError: () => toast.error("Couldn't start the in-play scan"),
  });
}

export function useSwingScreener(cap: "mega" | "small" = "mega", runId?: number | null) {
  return useQuery({
    queryKey: ["swing-screener", cap, runId ?? "latest"],
    queryFn: () =>
      api.get<SwingSnapshot>(`/screener/swing?cap=${cap}${runId ? `&run_id=${runId}` : ""}`),
    // Don't auto-refresh a pinned historical run; only the live "latest" view.
    refetchInterval: runId ? false : 120_000,
  });
}

export function useSwingHistory(cap: "mega" | "small" = "mega") {
  return useQuery({
    queryKey: ["swing-history", cap],
    queryFn: () => api.get<{ runs: SwingRun[] }>(`/screener/swing/history?cap=${cap}`),
  });
}

export function useRefreshSwing(cap: "mega" | "small" = "mega") {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post(`/screener/swing/refresh?cap=${cap}`, {}),
    onSuccess: () => {
      // Scan against ~130 symbols (mega + curated mid-cap universe) with
      // daily-bar fetches takes 30-90s. Single 9s refetch was firing
      // before the scan completed, leaving the user staring at unchanged
      // data. Poll every 15s up to 4 times so the UI catches up whenever
      // the scan actually finishes.
      toast.info("Swing scan started — results refresh as the scan completes (~60s)");
      const tries = [15000, 30000, 60000, 90000];
      tries.forEach((delay) => {
        setTimeout(() => {
          qc.invalidateQueries({ queryKey: ["swing-screener", cap, "latest"] });
          qc.invalidateQueries({ queryKey: ["swing-history", cap] });
        }, delay);
      });
    },
  });
}

// --- Conviction screener (analyst-backed long-term uptrends) ---

export function useConviction(runId?: number | null) {
  return useQuery({
    queryKey: ["conviction", runId ?? "latest"],
    queryFn: () =>
      api.get<ConvictionSnapshot>(`/screener/conviction${runId ? `?run_id=${runId}` : ""}`),
    refetchInterval: runId ? false : 5 * 60_000,  // saved runs are immutable
  });
}

export function useConvictionHistory() {
  return useQuery({
    queryKey: ["conviction-history"],
    queryFn: () => api.get<{ runs: ConvictionRun[] }>("/screener/conviction/history"),
  });
}

export function useRefreshConviction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post("/screener/conviction/refresh", {}),
    onSuccess: () => {
      // Analyst .info over the universe is slow (~60–120s). Poll a few times so
      // the table catches up when the scan finishes.
      toast.info("Conviction scan started — results refresh as it completes (~90s)");
      [20000, 45000, 75000, 110000].forEach((delay) =>
        setTimeout(() => {
          qc.invalidateQueries({ queryKey: ["conviction", "latest"] });
          qc.invalidateQueries({ queryKey: ["conviction-history"] });
        }, delay),
      );
    },
    onError: () => toast.error("Couldn't start the conviction scan"),
  });
}

/** Sync the latest conviction scan's Strong-Buy names into the platform
 *  watchlist (a "Conviction" group). The Pine acts on them via the TV
 *  watchlist — push those separately (scripts/tv_sync.py or MCP). */
export function useSyncConvictionWatchlist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api.post<{ added: string[]; skipped: string[]; strong_buy: string[] }>(
        "/screener/conviction/sync-watchlist",
        {},
      ),
    onSuccess: (res) => {
      const n = res.added.length;
      toast.success(
        n > 0
          ? `Added ${n} Strong-Buy name${n === 1 ? "" : "s"} to your Conviction watchlist group`
          : `Watchlist already up to date (${res.strong_buy.length} Strong-Buy names)`,
      );
      qc.invalidateQueries({ queryKey: ["watchlist"] });
    },
    onError: () => toast.error("Couldn't sync the conviction names to your watchlist"),
  });
}

// --- Weekly Stage screener (Weinstein 30-week-MA stage) ---

export function useWeeklyStage(runId?: number | null) {
  return useQuery({
    queryKey: ["weekly-stage", runId ?? "latest"],
    queryFn: () =>
      api.get<WeeklyStageSnapshot>(`/screener/weekly-stage${runId ? `?run_id=${runId}` : ""}`),
    refetchInterval: runId ? false : 5 * 60_000,  // weekly data; saved runs immutable
  });
}

export function useRefreshWeeklyStage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post("/screener/weekly-stage/refresh", {}),
    onSuccess: () => {
      // ~2y weekly bars over the full swing universe is slow (~60–120s). Poll a
      // few times so the table catches up when the scan finishes.
      toast.info("Weekly-stage scan started — results refresh as it completes (~90s)");
      [20000, 45000, 75000, 110000].forEach((delay) =>
        setTimeout(() => qc.invalidateQueries({ queryKey: ["weekly-stage", "latest"] }), delay),
      );
    },
    onError: () => toast.error("Couldn't start the weekly-stage scan"),
  });
}

// --- Social Buzz (Apewisdom-fed) ---

export interface SocialBuzzEntry {
  symbol: string;
  name: string;
  mentions: number;
  mentions_prev_24h: number;
  growth_pct: number | null;
  upvotes?: number;
  sentiment: string | null;          // "bullish" | "bearish" | "mixed" | null (from StockTwits)
  bullish_pct?: number;
  bearish_pct?: number;
  sentiment_score: number | null;
  sources?: string[];                // ["apewisdom"], ["stocktwits"], or both
  st_summary?: string;               // StockTwits "why it's trending" blurb
  st_watchers?: number;
  rank: number;
  has_grade_a_today: boolean;
  // Social value-adds (computed at refresh, read-only).
  earnings_in_days?: number | null;   // days to next earnings; UI gates on 0..7
  earnings_date?: string | null;      // YYYY-MM-DD
  accelerating?: boolean;             // mentions rising across recent snapshots
  mentions_history?: number[];        // oldest→newest, last ~6 readings (sparkline)
}

export interface SocialBuzzResponse {
  id?: number | null;
  captured_at: string | null;
  source: string | null;
  entries: SocialBuzzEntry[];
  stale: boolean;
}

export interface SocialBuzzRun {
  id: number;
  captured_at: string;
  count: number;
}

export function useSocialBuzz(runId?: number | null) {
  return useQuery({
    queryKey: ["social-buzz", runId ?? "latest"],
    queryFn: () =>
      api.get<SocialBuzzResponse>(`/screener/social-buzz${runId ? `?run_id=${runId}` : ""}`),
    refetchInterval: runId ? false : 5 * 60_000,  // saved runs are immutable; only latest polls
    staleTime: 60_000,
  });
}

export function useSocialBuzzHistory() {
  return useQuery({
    queryKey: ["social-buzz-history"],
    queryFn: () => api.get<{ runs: SocialBuzzRun[] }>("/screener/social-buzz/history"),
    staleTime: 60_000,
  });
}

interface SocialRefreshResult {
  status: string;
  fetched: number;
  after_filter?: number;
  snapshot_id?: number | null;
}

export function useRefreshSocialBuzz() {
  const qc = useQueryClient();
  return useMutation({
    // Synchronous now — returns the fetch summary so we can tell blocked from ok.
    mutationFn: () => api.post<SocialRefreshResult>("/screener/social-buzz/refresh", {}),
    onSuccess: (res) => {
      if (!res || res.fetched === 0) {
        toast.error("Social source unreachable right now — kept the last snapshot");
      } else {
        toast.success(`Social buzz refreshed — ${res.after_filter ?? 0} tickers`);
      }
      qc.invalidateQueries({ queryKey: ["social-buzz"] });
      qc.invalidateQueries({ queryKey: ["social-buzz-history"] });
    },
    onError: () => toast.error("Failed to refresh"),
  });
}

// --- Social Buzz CONTEXT (per-symbol StockTwits stream) ---

export interface SocialMessage {
  id: number;
  body: string;
  created_at: string;
  age_min: number;
  user: string;
  user_followers: number;
  sentiment: "bullish" | "bearish" | null;
}

export interface SocialBuzzContext {
  symbol: string;
  messages: SocialMessage[];
  bullish_count: number;
  bearish_count: number;
  neutral_count: number;
  total_count: number;
  bullish_pct: number;
  bearish_pct: number;
  neutral_pct: number;
  error?: string | null;
}

export function useSocialBuzzContext(symbol: string | null) {
  return useQuery({
    queryKey: ["social-buzz-context", symbol],
    queryFn: () =>
      api.get<SocialBuzzContext>(
        `/screener/social-buzz/context?symbol=${encodeURIComponent(symbol!)}`,
      ),
    enabled: !!symbol,           // only fires once user expands a row
    staleTime: 5 * 60_000,       // matches server cache TTL
  });
}

// --- Auth ---

export function useLogin() {
  return useMutation({
    mutationFn: (body: { email: string; password: string }) =>
      api.post<AuthTokens>("/auth/login", body),
  });
}

export function useRegister() {
  return useMutation({
    mutationFn: (body: { email: string; password: string; display_name?: string }) =>
      api.post<AuthTokens>("/auth/register", body),
  });
}

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: () => api.get<User>("/auth/me"),
    retry: false,
    staleTime: 5 * 60_000,
  });
}

// --- Watchlist ---

export interface WatchlistItem {
  id: number;
  symbol: string;
  group_id?: number | null;
  focus?: boolean;
}

export interface WatchlistGroup {
  id: number;
  name: string;
  sort_order: number;
  color: string;
}

export function useWatchlist() {
  return useQuery({
    queryKey: ["watchlist"],
    queryFn: () => api.get<WatchlistItem[]>("/watchlist"),
  });
}

export function useWatchlistGroups() {
  return useQuery({
    queryKey: ["watchlist-groups"],
    queryFn: () => api.get<WatchlistGroup[]>("/watchlist/groups"),
  });
}

// Public read-only view of the admin's watchlist ("Editor's Picks"). Every
// signed-in user can fetch this; UI surfaces it as a separate panel with a
// "+ Add to my watchlist" action per symbol and a "Copy all" bulk action.
// Refetch on focus so admin updates propagate quickly when users tab-switch.
export function useSectorsWatchlist() {
  return useQuery({
    queryKey: ["watchlist-sectors"],
    queryFn: () => api.get<WatchlistItem[]>("/watchlist/sectors"),
    staleTime: 60_000,
    refetchOnWindowFocus: true,
  });
}

// Copy the admin's full watchlist structure into the caller's account —
// preserving group names (Mega Tech, Chips, etc.) + colors + sort order.
// Idempotent: existing groups + items are left alone; only missing ones are
// added. Used by the "Copy all" button + the empty-state hero card.
export function useCopySectorsWatchlist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<WatchlistItem[]>("/watchlist/sectors/copy", {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["watchlist"] });
      qc.invalidateQueries({ queryKey: ["watchlist-groups"] });
      qc.invalidateQueries({ queryKey: ["scanner"] });
      qc.invalidateQueries({ queryKey: ["groups-premarket"] });
    },
  });
}

// --- Earnings (spec 61) ---

export interface UpcomingEarningsItem {
  symbol: string;
  next_earnings_date: string | null;        // YYYY-MM-DD
  days_until: number | null;
  time_of_day: string | null;               // BMO / AMC / DMH / null
  eps_estimate: number | null;
  revenue_estimate: number | null;
  confirmed: boolean;
  last_surprise_pct: number | null;
  last_quarter_label: string | null;
  last_reported_at: string | null;
  fetched_at: string | null;
}

export interface UpcomingEarningsResponse {
  items: UpcomingEarningsItem[];
  last_refreshed_at: string | null;
}

export function useUpcomingEarnings() {
  return useQuery({
    queryKey: ["earnings-upcoming"],
    queryFn: () => api.get<UpcomingEarningsResponse>("/earnings/upcoming"),
    staleTime: 60 * 60_000,  // earnings calendar changes ~once a quarter; 1h cache is fine
  });
}

// --- Fundamentals / Details tab ---

export interface AIBrief {
  summary?: string;
  business?: string;
  growth?: string;
  valuation?: string;
  analyst?: string;
  bull_case?: string;
  risks?: string;
  short_term?: string;
  long_term?: string;
  model?: string;
}

export interface FundMetrics {
  revenue_growth_pct: number | null;
  gross_margin_pct: number | null;
  net_margin_pct: number | null;
  week52_high: number | null;
  week52_low: number | null;
  last_price: number | null;
  ma50: number | null;
  ma200: number | null;
}

export interface FundamentalsItem {
  symbol: string;
  company_name: string | null;
  description: string | null;
  sector: string | null;
  industry: string | null;
  market_cap: number | null;
  trailing_eps: number | null;
  forward_eps: number | null;
  eps_growth_pct: number | null;
  pe_ratio: number | null;
  rec_strong_buy: number | null;
  rec_buy: number | null;
  rec_hold: number | null;
  rec_sell: number | null;
  rec_strong_sell: number | null;
  consensus: string | null;          // Buy / Hold / Sell
  rec_period: string | null;
  short_term_view: string | null;
  long_term_view: string | null;
  ai_brief: AIBrief | null;          // structured investment brief
  ai_generated_at: string | null;    // ISO; when the brief was generated
  metrics: FundMetrics | null;
  fetched_at: string | null;         // ISO; null = never fetched
}

export interface FundamentalsResponse {
  items: FundamentalsItem[];
  last_refreshed_at: string | null;
}

export function useWatchlistFundamentals() {
  return useQuery({
    queryKey: ["fundamentals-watchlist"],
    queryFn: () => api.get<FundamentalsResponse>("/fundamentals/watchlist"),
    staleTime: 60 * 60_000,  // fundamentals change slowly; cache is fine
  });
}

// On-demand refresh: pass a symbol to refresh one, or undefined for the whole
// watchlist. The server fetches + AI-generates synchronously, so the mutation
// resolves once the row is written; invalidate to re-read the cache.
export function useRefreshFundamentals() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbol?: string) =>
      api.post("/fundamentals/refresh", symbol ? { symbol } : { all: true }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["fundamentals-watchlist"] });
    },
  });
}

// Admin-only: (re)generate the structured AI brief (Sonnet) for a symbol or the
// whole watchlist. Heavier than the numbers refresh; poll a few times to catch up.
export function useGenerateAIBrief() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbol?: string) =>
      api.post("/fundamentals/ai-refresh", symbol ? { symbol } : { all: true }),
    onSuccess: (_d, symbol) => {
      toast.info(symbol ? `Generating AI brief for ${symbol}…` : "Generating AI briefs…");
      [8000, 20000, 40000, 70000].forEach((delay) =>
        setTimeout(() => qc.invalidateQueries({ queryKey: ["fundamentals-watchlist"] }), delay),
      );
    },
    onError: () => toast.error("Couldn't generate the AI brief"),
  });
}

// --- Weekly pattern report ---

export interface WeeklyPattern {
  alert_type: string;
  label: string;
  description?: string;
  fires: number;
  avg_vol_ratio: number | null;
  avg_vwap_slope_pct: number | null;
  pct_above_gates: number;
  graded?: number;                  // # of fires with computed real outcome
  real_worked_pct?: number | null;  // % of graded that hit +1R before -1R
  avg_mfe_r?: number | null;        // average max favorable excursion in R
}

export interface WeeklyFire {
  id: number;
  symbol: string;
  alert_type: string;
  label: string;
  description?: string;
  direction: string;
  created_at: string | null;
  volume_ratio: number | null;
  vwap_slope_pct: number | null;
  entry: number | null;
  stop: number | null;
  target_1: number | null;
}

export interface WeeklyReport {
  week_start: string;
  week_end: string;
  total_fires: number;
  unique_symbols: number;
  patterns: WeeklyPattern[];
  top_volume: WeeklyFire[];
  bottom_volume: WeeklyFire[];
}

export function useWeeklyReport(weekAnchor?: string) {
  return useQuery({
    queryKey: ["performance-weekly", weekAnchor ?? "current"],
    queryFn: () => api.get<WeeklyReport>(
      `/performance/weekly${weekAnchor ? `?week=${encodeURIComponent(weekAnchor)}` : ""}`,
    ),
    staleTime: 5 * 60_000,
  });
}

// --- Strategy Analysis (real forward returns + AI keep/stop) ---

export interface StrategyPattern {
  alert_type: string;
  label: string;
  description: string | null;
  n: number;
  avg_ret_eod: number | null;
  median_ret_eod: number | null;
  win_eod_pct: number | null;
  n_eow: number;
  avg_ret_eow: number | null;
  median_ret_eow: number | null;
  win_eow_pct: number | null;
  classification: "Swing" | "Day" | "Avoid";
  confidence: "low" | "ok";
  recommendation: "keep" | "stop" | "promote";
  // AI's independent verdict (from the cached structured response) + whether it
  // agrees with the rule engine's recommendation. null until AI has been run.
  ai_recommendation: "keep" | "stop" | "promote" | null;
  ai_classification: "Swing" | "Day" | "Avoid" | null;
  agree: boolean | null;
}

export type StrategyPeriod = "day" | "week";

export interface StrategyAnalysis {
  period?: StrategyPeriod;
  date?: string | null;            // day view: the resolved trading day
  available_days?: string[];       // day view: recent graded session dates (newest first)
  week_start?: string | null;      // week view
  week_end?: string | null;
  patterns: StrategyPattern[];
  ai_summary: string | null;
  agreement_pct: number | null;
  generated_at: string | null;
}

// Daily (rule-only) or Weekly (rule + on-demand AI). `date` anchors the day/week;
// omit to default to the latest graded day / current week.
export function useStrategyAnalysis(period: StrategyPeriod, date?: string) {
  return useQuery({
    queryKey: ["performance-strategy", period, date ?? "latest"],
    queryFn: () => api.get<StrategyAnalysis>(
      `/performance/strategy-analysis?period=${period}${date ? `&date=${date}` : ""}`,
    ),
    staleTime: 5 * 60_000,
  });
}

// Regenerate the weekly AI verdicts (admin only, on-demand). Invalidates the
// strategy query so the fresh narrative + per-pattern verdicts load.
export function useRefreshStrategyAnalysis() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (weekStart: string) =>
      api.post<StrategyAnalysis>(`/performance/strategy-analysis/refresh?period=week&date=${weekStart}`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["performance-strategy"] });
    },
  });
}

export function useSeedDefaultGroups() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<WatchlistGroup[]>("/watchlist/groups/seed-defaults", {}),
    onSuccess: () => {
      toast.success("Default groups seeded — Mega Tech, Chips, Memory, Optics, Cloud, Crypto, Fintech, Space, AI Data, Power, Speculation");
      qc.invalidateQueries({ queryKey: ["watchlist"] });
      qc.invalidateQueries({ queryKey: ["watchlist-groups"] });
    },
    onError: () => toast.error("Failed to seed default groups"),
  });
}

export function useCreateGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; color?: string; sort_order?: number }) =>
      api.post<WatchlistGroup>("/watchlist/groups", body),
    onSuccess: () => {
      toast.success("Group created");
      qc.invalidateQueries({ queryKey: ["watchlist-groups"] });
    },
    onError: () => toast.error("Failed to create group"),
  });
}

export function useDeleteGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (groupId: number) => api.delete(`/watchlist/groups/${groupId}`),
    onSuccess: () => {
      toast.success("Group deleted — items moved to Ungrouped");
      qc.invalidateQueries({ queryKey: ["watchlist-groups"] });
      qc.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });
}

export function useMoveItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, groupId }: { itemId: number; groupId: number | null }) =>
      api.patch<WatchlistItem>(`/watchlist/${itemId}`, { group_id: groupId }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });
}

// --- Premarket sector heat (per watchlist group) ---

export interface GroupSymbolQuote {
  symbol: string;
  last_price?: number | null;
  prior_close?: number | null;
  gap_pct?: number | null;
  volume?: number | null;
}

export interface GroupPremarketSummary {
  group_id: number;
  name: string;
  color: string;
  sort_order: number;
  item_count: number;
  avg_gap_pct: number | null;
  breadth_green: number;
  breadth_total: number;
  top_mover: GroupSymbolQuote | null;
  bottom_mover: GroupSymbolQuote | null;
  items: GroupSymbolQuote[];
}

export function useGroupsPremarket() {
  return useQuery({
    queryKey: ["groups-premarket"],
    queryFn: () => api.get<GroupPremarketSummary[]>("/market/groups/premarket-summary"),
    staleTime: 60_000,  // server caches 60s; client respects same window
  });
}

// --- Premarket Gap Board ---

export interface PremarketGapEntry {
  symbol: string;
  bucket: "clean" | "momentum";
  on_watchlist: boolean;
  gap_pct: number | null;
  gap_type: string | null;
  pm_last: number | null;
  pm_high: number | null;
  pm_low: number | null;
  pm_change_pct: number | null;
  pm_volume: number | null;
  pm_dollar_vol: number | null;
  prior_close: number | null;
  pdh: number | null;
  pdl: number | null;
  pwh: number | null;
  pwl: number | null;
  flags: string[];
  catalyst: string | null;
}

export interface PremarketGapsResponse {
  captured_at: string | null;
  entries: PremarketGapEntry[];
  stale: boolean;
}

export function usePremarketGaps() {
  return useQuery({
    queryKey: ["premarket-gaps"],
    queryFn: () => api.get<PremarketGapsResponse>("/market/premarket-gaps"),
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,  // premarket board changes as PM trades; poll lightly
  });
}

interface PremarketGapsRefreshResult {
  status: string;
  gappers?: number;
  scanned?: number;
  snapshot_id?: number | null;
}

export function useRefreshPremarketGaps() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<PremarketGapsRefreshResult>("/market/premarket-gaps/refresh", {}),
    onSuccess: (res) => {
      if (!res || res.gappers === 0) {
        toast.info("Premarket scan done — no gappers passing the filters right now");
      } else {
        toast.success(`Premarket gaps refreshed — ${res.gappers ?? 0} gappers`);
      }
      qc.invalidateQueries({ queryKey: ["premarket-gaps"] });
    },
    onError: () => toast.error("Premarket scan failed"),
  });
}

// --- SPY Regime (Feature 3) ---

export interface SpyRegimeSnapshot {
  status: "ok" | "unavailable";
  reason?: string;
  price?: number;
  vwap?: number;
  vwap_slope_pct?: number;
  today_open?: number;
  pdh?: number | null;
  pdl?: number | null;
  below_pdl?: boolean;   // SPY under its prior-day low → buy alerts suppressed
  inside_day?: boolean;
  rsi?: number | null;                                  // daily RSI(14)
  rsi_zone?: "oversold" | "overbought" | "neutral" | null;
  stale?: boolean;   // serving last-good snapshot (fresh fetch failed)
  bias?: "LONG" | "WAIT" | "NEUTRAL" | "STAND_DOWN";
  bias_label?: string;
  bias_color?: "green" | "amber" | "red" | "gray";
  last_bar_time?: string;
}

export function useSpyLiveRegime() {
  return useQuery({
    queryKey: ["spy-live-regime"],
    queryFn: () => api.get<SpyRegimeSnapshot>("/market/spy-regime"),
    refetchInterval: 60_000,   // 60s — server caches 30s, so worst-case 2 Alpaca pulls/min
    staleTime: 30_000,
  });
}

/** Live BTC regime — the crypto market gate (24/7). Same shape as SPY. */
export function useBtcLiveRegime() {
  return useQuery({
    queryKey: ["btc-live-regime"],
    queryFn: () => api.get<SpyRegimeSnapshot>("/market/btc-regime"),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}

/** Live prices — polls every 15 seconds during market hours. */
export function useLivePrices() {
  return useQuery({
    queryKey: ["live-prices"],
    queryFn: () => api.get<{ prices: Record<string, { price: number; change_pct: number }> }>("/market/prices"),
    refetchInterval: 15_000,  // 15 seconds
    staleTime: 10_000,
  });
}

export function useAddSymbol() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbol: string) => api.post<WatchlistItem>("/watchlist", { symbol }),
    onMutate: async (symbol) => {
      await qc.cancelQueries({ queryKey: ["watchlist"] });
      const prev = qc.getQueryData<WatchlistItem[]>(["watchlist"]);
      qc.setQueryData<WatchlistItem[]>(["watchlist"], (old) => [
        ...(old ?? []),
        { id: Date.now(), symbol },
      ]);
      return { prev };
    },
    onError: (_err, _sym, ctx) => {
      if (ctx?.prev) qc.setQueryData(["watchlist"], ctx.prev);
      toast.error("Failed to add symbol");
    },
    onSuccess: (_data, symbol) => toast.success(`${symbol} added`),
    onSettled: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });
}

// Add a symbol into a specific watchlist group (e.g. the "Trending" group used
// by the Social feed). Backend POST /watchlist already accepts group_id and
// validates group ownership.
export function useAddSymbolToGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ symbol, groupId }: { symbol: string; groupId: number }) =>
      api.post<WatchlistItem>("/watchlist", { symbol, group_id: groupId }),
    onSuccess: (_d, v) => toast.success(`${v.symbol} added to Trending`),
    onError: () => toast.error("Failed to add symbol"),
    onSettled: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });
}

export function useRemoveSymbol() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbol: string) => api.delete(`/watchlist/${symbol}`),
    onMutate: async (symbol) => {
      await qc.cancelQueries({ queryKey: ["watchlist"] });
      const prev = qc.getQueryData<WatchlistItem[]>(["watchlist"]);
      qc.setQueryData<WatchlistItem[]>(["watchlist"], (old) =>
        (old ?? []).filter((w) => w.symbol !== symbol),
      );
      return { prev };
    },
    onError: (_err, _sym, ctx) => {
      if (ctx?.prev) qc.setQueryData(["watchlist"], ctx.prev);
      toast.error("Failed to remove symbol");
    },
    onSuccess: (_data, symbol) => toast.success(`${symbol} removed`),
    onSettled: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });
}

// Toggle the "Focus today" flag on a watchlist symbol. Visual-only filter
// for the Trading sidebar — alert routing/Telegram are unaffected.
// Optimistic flip so the star feels instant; rollback on error.
export function useToggleWatchlistFocus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbol: string) => api.post<WatchlistItem>(`/watchlist/focus/${symbol}`, {}),
    onMutate: async (symbol) => {
      await qc.cancelQueries({ queryKey: ["watchlist"] });
      const prev = qc.getQueryData<WatchlistItem[]>(["watchlist"]);
      qc.setQueryData<WatchlistItem[]>(["watchlist"], (old) =>
        (old ?? []).map((w) => (w.symbol === symbol ? { ...w, focus: !w.focus } : w)),
      );
      return { prev };
    },
    onError: (_err, _sym, ctx) => {
      if (ctx?.prev) qc.setQueryData(["watchlist"], ctx.prev);
      toast.error("Couldn't update focus");
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });
}

// Clear every focus flag for the caller — the "Reset focus" action.
export function useClearWatchlistFocus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post("/watchlist/focus/clear", {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });
}

export function useBulkSetWatchlist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbols: string[]) => api.put<WatchlistItem[]>("/watchlist", { symbols }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });
}

// --- Scanner ---

export function useScanner() {
  return useQuery({
    queryKey: ["scanner"],
    queryFn: () => api.get<SignalResult[]>("/scanner/scan"),
    staleTime: 60_000, // 60s — prices come from live feed now
    refetchInterval: 60_000, // refresh grades/scores every 60s
  });
}

export function useWatchlistRank() {
  return useQuery({
    queryKey: ["watchlist-rank"],
    queryFn: () => api.get<import("../types").WatchlistRankItem[]>("/scanner/watchlist-rank"),
    staleTime: 3 * 60_000,  // 3 min — matches backend cache TTL
    refetchInterval: 3 * 60_000,
    // Keep prior data visible during refetch — avoids row flicker every 3min.
    placeholderData: (prev) => prev,
  });
}

export function useActiveEntries() {
  return useQuery({
    queryKey: ["active-entries"],
    queryFn: () =>
      api.get<
        {
          id: number;
          symbol: string;
          entry_price: number | null;
          stop_price: number | null;
          target_1: number | null;
          target_2: number | null;
          alert_type: string | null;
          status: string;
        }[]
      >("/scanner/active-entries"),
  });
}

// --- Market ---

export interface MarketStatus {
  is_open: boolean;
  is_premarket: boolean;
  session_phase: string;
}

export function useMarketStatus() {
  return useQuery({
    queryKey: ["market-status"],
    queryFn: () => api.get<MarketStatus>("/market/status"),
    refetchInterval: 60_000,
  });
}

export interface OHLCBar {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export function useIntraday(symbol: string) {
  return useQuery({
    queryKey: ["intraday", symbol],
    queryFn: () => api.get<OHLCBar[]>(`/market/intraday/${symbol}`),
    enabled: !!symbol,
    staleTime: 3 * 60_000,
  });
}

export function usePriorDay(symbol: string) {
  return useQuery({
    queryKey: ["prior-day", symbol],
    queryFn: () => api.get<Record<string, unknown>>(`/market/prior-day/${symbol}`),
    enabled: !!symbol,
    staleTime: 5 * 60_000,
  });
}

export interface SectorRotationItem {
  symbol: string;
  name: string;
  price: number;
  change_1d: number;
  change_5d: number;
  change_20d: number;
  flow: "INFLOW" | "OUTFLOW" | "NEUTRAL";
}

export function useSectorRotation() {
  return useQuery({
    queryKey: ["sector-rotation"],
    queryFn: () => api.get<SectorRotationItem[]>("/market/sector-rotation"),
    staleTime: 5 * 60_000,
    refetchInterval: 5 * 60_000,
  });
}

// --- Catalysts ---

export interface CatalystItem {
  symbol: string;
  event: string;  // "EARNINGS" | "EX_DIVIDEND" | "DIVIDEND"
  date: string;
  days_away: number;
  timing?: string;  // "After Close" | "Before Open" | "Unknown"
}

/** Upcoming catalysts (earnings, ex-dividend) — refreshes every 30 min. */
export function useCatalysts(symbols: string) {
  return useQuery({
    queryKey: ["catalysts", symbols],
    queryFn: () => api.get<CatalystItem[]>(`/market/catalysts?symbols=${encodeURIComponent(symbols)}`),
    enabled: !!symbols,
    staleTime: 30 * 60_000,  // 30 min — catalysts don't change often
    refetchInterval: 30 * 60_000,
  });
}

/** Options flow — unusual options activity scanner, refreshes every 3 min. */
export function useOptionsFlow(symbols: string) {
  return useQuery({
    queryKey: ["options-flow", symbols],
    queryFn: () => api.get<import("../types").OptionsFlowItem[]>(`/market/options-flow?symbols=${encodeURIComponent(symbols)}`),
    enabled: !!symbols,
    staleTime: 3 * 60_000,
    refetchInterval: 3 * 60_000,
  });
}

// --- Alerts ---

export function useAlertsToday() {
  return useQuery({
    queryKey: ["alerts-today"],
    queryFn: () => api.get<Alert[]>("/alerts/today"),
    refetchInterval: 20_000, // refresh every 20s to catch new alerts
    // Keep polling even when the tab is backgrounded — otherwise signal
    // notifications would only fire while you're looking at the tab.
    refetchIntervalInBackground: true,
  });
}

export interface UsageStatus {
  tier: string;
  trial_active: boolean;
  trial_days_left: number;
  limits: Record<string, unknown>;
  usage_today: Record<string, number>;
  ai_scan_alerts_today: number;
  ai_scan_alerts_max: number | null;
  ai_scan_limit_reached: boolean;
}

export function useUsageStatus() {
  return useQuery({
    queryKey: ["usage-status"],
    queryFn: () => api.get<UsageStatus>("/auth/usage"),
    refetchInterval: 60_000, // 1 min
  });
}

export function useAlertsHistory(days = 7) {
  return useQuery({
    queryKey: ["alerts-history", days],
    queryFn: () => api.get<Alert[]>(`/alerts/history?days=${days}`),
  });
}

export interface SessionSummary {
  total_alerts: number;
  buy_alerts: number;
  sell_alerts: number;
  target_1_hits: number;
  target_2_hits: number;
  stopped_out: number;
  active_entries: number;
}

export function useSessionSummary() {
  return useQuery({
    queryKey: ["session-summary"],
    queryFn: () => api.get<SessionSummary>("/alerts/session-summary"),
    refetchInterval: 60_000,
  });
}

// --- Trades ---

export interface TradeHistoryItem {
  symbol: string;
  trade_date: string;
  proceeds: number;
  cost_basis: number;
  realized_pnl: number;
  wash_sale_disallowed: number;
  asset_type: string | null;
  holding_days: number | null;
  account: string | null;
  source: string;
}

export function useTradeHistory() {
  return useQuery({
    queryKey: ["trade-history"],
    queryFn: () => api.get<TradeHistoryItem[]>("/trades/history"),
  });
}

export interface MonthlyStats {
  month: string;
  total_trades: number;
  total_pnl: number;
  win_count: number;
  loss_count: number;
  win_rate: number;
}

export function useMonthlyStats() {
  return useQuery({
    queryKey: ["monthly-stats"],
    queryFn: () => api.get<MonthlyStats[]>("/trades/monthly-stats"),
  });
}

// --- Charts ---

export interface ChartLevel {
  id: number;
  symbol: string;
  price: number;
  label: string;
  color: string;
}

export function useChartLevels(symbol: string) {
  return useQuery({
    queryKey: ["chart-levels", symbol],
    queryFn: () => api.get<ChartLevel[]>(`/charts/levels?symbol=${symbol}`),
    enabled: !!symbol,
  });
}

export function useAddChartLevel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { symbol: string; price: number; label?: string; color?: string }) =>
      api.post<ChartLevel>("/charts/levels", body),
    onSuccess: (lvl, vars) => {
      qc.invalidateQueries({ queryKey: ["chart-levels", vars.symbol] });
      toast.success(`Line added at $${lvl.price.toFixed(2)}`);
    },
    onError: () => toast.error("Couldn't add the line"),
  });
}

export function useUpdateChartLevel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: number; symbol: string; price?: number; label?: string; color?: string }) =>
      api.put<ChartLevel>(`/charts/levels/${vars.id}`, {
        price: vars.price, label: vars.label, color: vars.color,
      }),
    onSuccess: (_, vars) => qc.invalidateQueries({ queryKey: ["chart-levels", vars.symbol] }),
  });
}

export function useDeleteChartLevel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: number; symbol: string }) =>
      api.delete(`/charts/levels/${vars.id}`),
    onSuccess: (_, vars) => qc.invalidateQueries({ queryKey: ["chart-levels", vars.symbol] }),
  });
}

export function useOHLCV(symbol: string, period = "1y", interval = "1d") {
  // Chart data: refresh every 10s for intraday, 60s for daily
  const isIntraday = ["1m", "5m", "15m", "30m", "60m"].includes(interval);
  const refreshMs = isIntraday ? 10_000 : 60_000;
  return useQuery({
    queryKey: ["ohlcv", symbol, period, interval],
    queryFn: () => api.get<OHLCBar[]>(`/charts/ohlcv/${symbol}?period=${period}&interval=${interval}`),
    enabled: !!symbol,
    staleTime: refreshMs,
    refetchInterval: refreshMs,
    gcTime: 30 * 60_000,
  });
}

// --- Real Trades ---

export interface RealTrade {
  id: number;
  symbol: string;
  direction: string;
  shares: number;
  entry_price: number;
  exit_price: number | null;
  stop_price: number | null;
  target_price: number | null;
  pnl: number | null;
  status: string;
  notes: string | null;
  session_date: string;
  opened_at: string;
  closed_at: string | null;
}

/** Dismiss a trade you didn't actually take — removes it from open positions (#64 I). */
export function useDeleteTrade() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.delete(`/real-trades/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["real-trades-open"] }); },
  });
}

export function useOpenTrades() {
  return useQuery({
    queryKey: ["real-trades-open"],
    queryFn: () => api.get<RealTrade[]>("/real-trades/open"),
    staleTime: 15_000, // refetch every 15s to catch new positions
  });
}

export function useClosedTrades(limit = 50) {
  return useQuery({
    queryKey: ["real-trades-closed", limit],
    queryFn: () => api.get<RealTrade[]>(`/real-trades/closed?limit=${limit}`),
  });
}

export function useCloseTrade() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, exit_price, notes }: { id: number; exit_price: number; notes?: string }) =>
      api.post<RealTrade>(`/real-trades/${id}/close`, { exit_price, notes: notes || "" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["real-trades-open"] });
      qc.invalidateQueries({ queryKey: ["real-trades-closed"] });
      qc.invalidateQueries({ queryKey: ["real-trade-stats"] });
      toast.success("Position closed");
    },
    onError: () => toast.error("Failed to close position"),
  });
}

export interface RealTradeStats {
  total_pnl: number;
  total_trades: number;
  win_count: number;
  loss_count: number;
  win_rate: number;
  avg_win: number;
  avg_loss: number;
  expectancy: number;
}

export function useRealTradeStats() {
  return useQuery({
    queryKey: ["real-trade-stats"],
    queryFn: () => api.get<RealTradeStats>("/real-trades/stats"),
  });
}

export function useOpenRealTrade() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      symbol: string;
      direction?: string;
      entry_price: number;
      stop_price?: number;
      target_price?: number;
      shares?: number;
    }) => api.post<RealTrade>("/real-trades/open", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["real-trades-open"] }),
  });
}

export function useCloseRealTrade() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, exit_price, notes }: { id: number; exit_price: number; notes?: string }) =>
      api.post<RealTrade>(`/real-trades/${id}/close`, { exit_price, notes }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["real-trades-open"] });
      qc.invalidateQueries({ queryKey: ["real-trades-closed"] });
      qc.invalidateQueries({ queryKey: ["real-trade-stats"] });
    },
  });
}

// --- Paper Trading ---

export interface PaperTrade {
  id: number;
  symbol: string;
  direction: string;
  shares: number;
  entry_price: number | null;
  exit_price: number | null;
  pnl: number | null;
  status: string;
  session_date: string;
}

export function usePaperPositions() {
  return useQuery({
    queryKey: ["paper-positions"],
    queryFn: () => api.get<PaperTrade[]>("/paper-trading/positions"),
  });
}

export function usePaperHistory() {
  return useQuery({
    queryKey: ["paper-history"],
    queryFn: () => api.get<PaperTrade[]>("/paper-trading/history"),
  });
}

export interface PaperAccount {
  open_positions: number;
  total_closed: number;
  total_pnl: number;
  win_rate: number;
}

export function usePaperAccount() {
  return useQuery({
    queryKey: ["paper-account"],
    queryFn: () => api.get<PaperAccount>("/paper-trading/account"),
  });
}

// --- Per-alert exit price + by-alert-type performance (Trades page) ---

export interface AlertTypePerformance {
  alert_type: string;
  label: string;
  description?: string;
  took: number;
  with_exit: number;
  wins: number;
  win_rate: number | null;
  avg_r: number | null;
  best_r: number | null;
  worst_r: number | null;
}

export function useAlertTypePerformance() {
  return useQuery({
    queryKey: ["alert-type-performance"],
    queryFn: () => api.get<{ items: AlertTypePerformance[] }>("/alerts/by-alert-type-performance"),
  });
}

export function useSetAlertExit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ alertId, exitPrice }: { alertId: number; exitPrice: number | null }) =>
      api.post<{ id: number; exit_price: number | null; r_multiple: number | null }>(
        `/alerts/${alertId}/exit`,
        { exit_price: exitPrice },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alerts-today"] });
      qc.invalidateQueries({ queryKey: ["alerts-history"] });
      qc.invalidateQueries({ queryKey: ["alert-type-performance"] });
    },
  });
}

// --- Backtest ---

export interface BacktestResult {
  symbol: string;
  total_signals: number;
  win_count: number;
  loss_count: number;
  win_rate: number;
  total_pnl: number;
  avg_rr: number;
}

/** Self-report a taken trade with the user's ACTUAL entry + exit (#64 Sub-spec I).
 *  exit=null → position open. Returns the computed outcome (win/loss + r_multiple). */
export function useReportTrade() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ alertId, entry, exit }: { alertId: number; entry: number; exit: number | null }) =>
      api.post<{ id: number; user_action: string; entry: number; exit_price: number | null; r_multiple: number | null; outcome: string | null; status: string }>(
        `/alerts/${alertId}/report`,
        { entry, exit },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alerts-today"] });
      qc.invalidateQueries({ queryKey: ["alert-type-performance"] });
    },
  });
}

export function useRunBacktest() {
  return useMutation({
    mutationFn: (body: { symbols: string[]; start_date: string; end_date: string }) =>
      api.post<BacktestResult[]>("/backtest/run", body),
  });
}

// --- Alert ACK ---

export function useAckAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action }: { id: number; action: "took" | "skipped" }) =>
      api.post(`/alerts/${id}/ack?action=${action}`),
    onMutate: async ({ id, action }) => {
      await qc.cancelQueries({ queryKey: ["alerts-today"] });
      const prev = qc.getQueryData<Alert[]>(["alerts-today"]);
      qc.setQueryData<Alert[]>(["alerts-today"], (old) =>
        (old ?? []).map((a) => a.id === id ? { ...a, user_action: action } : a),
      );
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(["alerts-today"], ctx.prev);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["alerts-today"] });
      qc.invalidateQueries({ queryKey: ["session-summary"] });
      qc.invalidateQueries({ queryKey: ["real-trades-open"] });
    },
  });
}

export function useSetAlertOutcome() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, outcome }: { id: number; outcome: "worked" | "failed" | "clear" }) =>
      api.post(`/alerts/${id}/outcome?outcome=${outcome}`),
    onMutate: async ({ id, outcome }) => {
      await qc.cancelQueries({ queryKey: ["alerts-today"] });
      const prev = qc.getQueryData<Alert[]>(["alerts-today"]);
      qc.setQueryData<Alert[]>(["alerts-today"], (old) =>
        (old ?? []).map((a) =>
          a.id === id ? { ...a, outcome: outcome === "clear" ? null : outcome } : a),
      );
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(["alerts-today"], ctx.prev);
    },
    onSettled: () => {
      qc.invalidateQueries({
        predicate: (query) => {
          const k = String(query.queryKey?.[0] ?? "");
          return k.startsWith("alerts") || k === "scorecard";
        },
      });
    },
  });
}

export function useScorecard(date = "") {
  return useQuery({
    queryKey: ["scorecard", date],
    queryFn: () =>
      api.get<{ session_date: string; items: ScorecardItem[] }>(
        `/alerts/scorecard?session_date=${date}`,
      ),
  });
}

export function useAlertSessionDates() {
  return useQuery({
    queryKey: ["alert-session-dates"],
    queryFn: () => api.get<string[]>("/alerts/session-dates"),
  });
}

export function useAlertSession(date: string) {
  return useQuery({
    queryKey: ["alert-session", date],
    queryFn: () => api.get<SessionSummary>(`/alerts/session/${date}`),
    enabled: !!date,
  });
}

export function useAlertsForDate(date: string) {
  return useQuery({
    queryKey: ["alerts-date", date],
    queryFn: () => api.get<Alert[]>(`/alerts/history?days=90`),
    enabled: !!date,
    // Return ALL alerts for the date — the live Signals feed (TradingPageV2) shares
    // this hook and needs the suppressed rows for its Muted / Not-routed tabs. The
    // delivered-only filter for the EOD report belongs in EODReportPage, NOT here
    // (#227 wrongly filtered here and emptied the live feed's Muted/Not-routed tabs).
    select: (data) => data.filter((a) => a.session_date === date),
  });
}

// --- Performance Breakdown ---

export function usePerformanceBreakdown() {
  return useQuery({
    queryKey: ["performance-breakdown"],
    queryFn: () => api.get<PerformanceBreakdown>("/real-trades/performance-breakdown"),
    staleTime: 5 * 60_000,
  });
}

// --- Real Trade Notes ---

export function useUpdateTradeNotes() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, notes }: { id: number; notes: string }) =>
      api.put(`/real-trades/${id}/notes`, { notes }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["real-trades-open"] });
      qc.invalidateQueries({ queryKey: ["real-trades-closed"] });
    },
  });
}

// --- Equity Curves ---

export function useRealTradeEquityCurve() {
  return useQuery({
    queryKey: ["real-trades-equity"],
    queryFn: () => api.get<EquityPoint[]>("/real-trades/equity-curve"),
  });
}

export function usePaperEquityCurve() {
  return useQuery({
    queryKey: ["paper-equity"],
    queryFn: () => api.get<EquityPoint[]>("/paper-trading/equity-curve"),
  });
}

export function useImportedEquityCurve() {
  return useQuery({
    queryKey: ["imported-equity"],
    queryFn: () => api.get<EquityPoint[]>("/trades/equity-curve"),
  });
}

// --- Options Trades ---

export function useOpenOptionsTrades() {
  return useQuery({
    queryKey: ["options-open"],
    queryFn: () => api.get<OptionsTrade[]>("/real-trades/options/open"),
  });
}

export function useClosedOptionsTrades(limit = 200) {
  return useQuery({
    queryKey: ["options-closed", limit],
    queryFn: () => api.get<OptionsTrade[]>(`/real-trades/options/closed?limit=${limit}`),
  });
}

export function useOptionsTradeStats() {
  return useQuery({
    queryKey: ["options-stats"],
    queryFn: () => api.get<OptionsTradeStats>("/real-trades/options/stats"),
  });
}

export function useOpenOptionsTrade() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      symbol: string;
      option_type: string;
      strike: number;
      expiration: string;
      contracts?: number;
      premium_per_contract: number;
    }) => api.post("/real-trades/options/open", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["options-open"] }),
  });
}

export function useCloseOptionsTrade() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, exit_premium, notes }: { id: number; exit_premium: number; notes?: string }) =>
      api.post(`/real-trades/options/${id}/close`, { exit_premium, notes }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["options-open"] });
      qc.invalidateQueries({ queryKey: ["options-closed"] });
      qc.invalidateQueries({ queryKey: ["options-stats"] });
    },
  });
}

// --- Settings ---

export function useUpdateProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { display_name: string }) =>
      api.put("/settings/profile", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (body: { current_password: string; new_password: string }) =>
      api.put("/settings/password", body),
  });
}

export function useNotificationPrefs() {
  return useQuery({
    queryKey: ["notification-prefs"],
    queryFn: () => api.get<NotificationPrefs>("/settings/notifications"),
  });
}

export function useUpdateNotificationPrefs() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: NotificationPrefs) =>
      api.put<NotificationPrefs>("/settings/notifications", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notification-prefs"] }),
  });
}

// --- Per-Alert-Type Channel Routing ---

export function useNotificationRouting() {
  return useQuery({
    queryKey: ["notification-routing"],
    queryFn: () => api.get<NotificationRouting>("/settings/notification-routing"),
  });
}

export function useUpdateNotificationRouting() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: NotificationRouting) => {
      const { telegram_update_symbols, ...routing } = data;
      return api.put<NotificationRouting>("/settings/notification-routing", {
        routing,
        telegram_update_symbols,
      });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notification-routing"] }),
  });
}

// --- Alert Preferences ---

export function useAlertPrefs() {
  return useQuery({
    queryKey: ["alert-prefs"],
    queryFn: () => api.get<import("../types").AlertPrefs>("/settings/alert-preferences"),
  });
}

export function useUpdateAlertPrefs() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { categories: Record<string, boolean>; min_score: number }) =>
      api.put<import("../types").AlertPrefs>("/settings/alert-preferences", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alert-prefs"] }),
  });
}

// --- Telegram ---

export function useTelegramStatus() {
  return useQuery({
    queryKey: ["telegram-status"],
    queryFn: () => api.get<{ linked: boolean; telegram_enabled: boolean }>("/settings/telegram-status"),
  });
}

export function useTelegramLink() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<{ deep_link: string; token: string }>("/settings/telegram-link"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["telegram-status"] }),
  });
}

export function useTelegramUnlink() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.delete("/settings/telegram-link"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["telegram-status"] }),
  });
}

// --- Swing Trades ---

export function useSpyRegime() {
  return useQuery({
    queryKey: ["spy-regime"],
    queryFn: () => api.get<SpyRegime>("/swing/regime"),
    staleTime: 5 * 60_000,
  });
}

export function useActiveSwingTrades() {
  return useQuery({
    queryKey: ["swing-active"],
    queryFn: () => api.get<SwingTrade[]>("/swing/trades/active"),
  });
}

export function useSwingTradesHistory(limit = 50) {
  return useQuery({
    queryKey: ["swing-history", limit],
    queryFn: () => api.get<SwingTrade[]>(`/swing/trades/history?limit=${limit}`),
  });
}

export interface SwingScanResult {
  alerts_fired: number;
  symbols_scanned?: number | null;
  symbols_qualified?: number | null;
  fetch_failures?: number | null;
  regime?: string | null;
  error?: string | null;
}

export function useTriggerSwingScan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<SwingScanResult>("/swing/scan"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["swing-active"] });
      qc.invalidateQueries({ queryKey: ["swing-history"] });
    },
  });
}

// --- Intel Hub ---

export function useAlertWinRates(days = 90) {
  return useQuery({
    queryKey: ["alert-win-rates", days],
    queryFn: () => api.get<WinRateData>(`/intel/win-rates?days=${days}`),
    staleTime: 10 * 60_000,
  });
}

export function useAckedWinRates(days = 90) {
  return useQuery({
    queryKey: ["acked-win-rates", days],
    queryFn: () => api.get<WinRateData>(`/intel/acked-win-rates?days=${days}`),
    staleTime: 10 * 60_000,
  });
}

export function useFundamentals(symbol: string) {
  return useQuery({
    queryKey: ["fundamentals", symbol],
    queryFn: () => api.get<{ symbol: string; data: Record<string, unknown> }>(`/intel/fundamentals/${symbol}`),
    enabled: !!symbol,
    staleTime: 30 * 60_000,
  });
}

export function useDailyAnalysis(symbol: string) {
  return useQuery({
    queryKey: ["daily-analysis", symbol],
    queryFn: () => api.get<SetupAnalysis>(`/intel/daily/${symbol}`),
    enabled: !!symbol,
    staleTime: 5 * 60_000,
  });
}

export function useWeeklyAnalysis(symbol: string) {
  return useQuery({
    queryKey: ["weekly-analysis", symbol],
    queryFn: () => api.get<SetupAnalysis>(`/intel/weekly/${symbol}`),
    enabled: !!symbol,
    staleTime: 30 * 60_000,
  });
}

export function useMTFContext(symbol: string) {
  return useQuery({
    queryKey: ["mtf-context", symbol],
    queryFn: () => api.get<MTFContext>(`/intel/mtf/${symbol}`),
    enabled: !!symbol,
    staleTime: 5 * 60_000,
  });
}

// --- Performance Analytics ---

export interface StrategyPerformance {
  alert_type: string;
  total: number;
  wins: number;
  losses: number;
  no_outcome: number;
  t2_wins: number;
  win_rate: number;
  avg_score: number;
  avg_confluence: number;
}

export function usePerformanceByStrategy() {
  return useQuery({
    queryKey: ["performance-by-strategy"],
    queryFn: () => api.get<StrategyPerformance[]>("/performance/by-strategy"),
    staleTime: 10 * 60_000,
  });
}

export function usePerformanceSummary() {
  return useQuery({
    queryKey: ["performance-summary"],
    queryFn: () => api.get<Record<string, number>>("/performance/summary"),
    staleTime: 10 * 60_000,
  });
}

// --- Game Plan ---

export interface GamePlanSetup {
  symbol: string;
  direction: string;
  action_label: string;
  score: number;
  confluence_score: number;
  confluence_label: string;
  entry: number | null;
  stop: number | null;
  target_1: number | null;
  target_2: number | null;
  rr_ratio: number | null;
  risk_per_share: number | null;
  support_status: string;
  pattern: string;
  bias: string;
  composite_score: number;
}

export function useGamePlan() {
  return useQuery({
    queryKey: ["game-plan"],
    queryFn: () => api.get<GamePlanSetup[]>("/intel/game-plan"),
    staleTime: 5 * 60_000,
  });
}

// --- Trade Journal ---

export interface JournalEntry {
  id: number;
  symbol: string;
  alert_type: string;
  direction: string;
  entry_price: number | null;
  exit_price: number | null;
  stop_price: number | null;
  target_1: number | null;
  target_2: number | null;
  outcome: string;
  pnl_r: number | null;
  replay_text: string | null;
  session_date: string;
  created_at: string;
}

export function useTradeJournal(date?: string) {
  return useQuery({
    queryKey: ["trade-journal", date],
    queryFn: () => api.get<JournalEntry[]>(`/intel/trade-journal${date ? `?date=${date}` : ""}`),
    staleTime: 5 * 60_000,
  });
}

// --- Focus List (persisted Best Setups, spec 55) ---

export type TradeHorizon = "day_trade" | "swing";
export type MarketWindow = "pre_open" | "pre_close" | "other";
export type FocusListStatus = "has_setups" | "no_setups" | "failed";

export interface QualifyingCriteria {
  entry_trigger: string;
  conviction_drivers: string[];
  horizon_fit: TradeHorizon;
}

export interface FocusRecommendation {
  symbol: string;
  setup_type: string;
  direction: "LONG" | "SHORT";
  trade_horizon: TradeHorizon;
  conviction: "HIGH" | "MEDIUM" | "LOW";
  entry: number;
  stop: number | null;
  t1: number | null;
  t2: number | null;
  current_price: number;
  distance_to_entry_pct: number;
  confluence: string[];
  why_now: string;
  qualifying_criteria: QualifyingCriteria;
  grade?: string;
  vol_ratio?: number;
}

export interface FocusList {
  id: number;
  generated_at: string;
  session_date: string;
  market_window: MarketWindow;
  status: FocusListStatus;
  watchlist_size: number;
  recommendations: FocusRecommendation[];
  skipped: { symbol: string; reason: string }[];
  message: string | null;
  is_stale?: boolean;
}

export interface FocusListRunResponse extends Partial<FocusList> {
  cadence_check: boolean;
  cadence_exceeded?: boolean;
  runs_today?: number;
}

export interface FocusListHistoryItem {
  id: number;
  generated_at: string;
  session_date: string;
  market_window: MarketWindow;
  status: FocusListStatus;
  recommendation_count: number;
}

/** The current saved focus list. Returns undefined when none exists (HTTP 204). */
export function useLatestFocusList() {
  return useQuery({
    queryKey: ["focus-list", "latest"],
    queryFn: () => api.get<FocusList | undefined>("/ai/focus-lists/latest"),
    retry: false,
    staleTime: 5 * 60_000,
  });
}

export function useFocusListHistory() {
  return useQuery({
    queryKey: ["focus-list", "history"],
    queryFn: () =>
      api.get<{ items: FocusListHistoryItem[]; total: number }>("/ai/focus-lists"),
    retry: false,
    staleTime: 5 * 60_000,
  });
}

export function useFocusListDetail(id: number | null) {
  return useQuery({
    queryKey: ["focus-list", "detail", id],
    queryFn: () => api.get<FocusList>(`/ai/focus-lists/${id}`),
    enabled: id != null,
    retry: false,
    staleTime: 5 * 60_000,
  });
}

/** Run the scan + persist. Pass { force: true } to proceed past the cadence check. */
export function useRunFocusList() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (opts?: { force?: boolean }) =>
      api.post<FocusListRunResponse>(
        `/ai/focus-lists/run${opts?.force ? "?force=true" : ""}`,
      ),
    onSuccess: (data) => {
      // A cadence pre-check returns without running — nothing to invalidate.
      if (!data.cadence_check) {
        qc.invalidateQueries({ queryKey: ["focus-list"] });
      }
    },
    onError: (err: { message?: string; detail?: { message?: string } }) => {
      toast.error(err.detail?.message || err.message || "Scan failed");
    },
  });
}

// --- Alert Type toggles (per-type enable/disable) ---

export interface AlertTypeConfigItem {
  alert_type: string;
  label: string;
  category: string;
  enabled: boolean;
  description?: string;
}

export function useAlertConfig() {
  return useQuery({
    queryKey: ["alert-config"],
    queryFn: () => api.get<AlertTypeConfigItem[]>("/alert-config"),
    staleTime: 60_000,
    retry: false,
  });
}

/** Gate config — the SPY-trend long gate + the multi-touch notice symbol
 *  allowlist (re-added 2026-06-10). The old per-symbol master switch was
 *  removed 2026-06-09; alert delivery = Alert Types + these. */
export interface RegimeExemptConfig {
  spy_trend_gate_enabled: string;  // "true"/"false" — block longs when SPY below its 8 & 21 EMA
  spy_trend_exempt: string;  // symbols still allowed to fire longs when SPY has rolled over
  rc_4h_short_symbols: string;  // superseded by short_symbols (#278); kept for back-compat
  short_symbols: string;  // symbols whose SHORT alerts (any type) flow; blank = none (#278)
  ma_alert_symbols: string;  // symbols whose MA/EMA bounce alerts fire; blank = none (#282)
  rc_symbols: string;  // symbols whose 4h RC alerts (long + short) fire; blank = none (#286)
  gap_always_symbols: string;  // symbols whose gap-and-go always delivers even when gap-and-go is muted (default SPY,QQQ)
  htf_sr_symbols: string;  // symbols allowed to deliver the multi-period S/R reject/bounce (default SPY,QQQ)
}

export function useRegimeConfig() {
  return useQuery({
    queryKey: ["regime-config"],
    queryFn: () => api.get<RegimeExemptConfig>("/regime-config"),
    staleTime: 60_000,
    retry: false,
  });
}

export function useUpdateRegimeConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: Partial<RegimeExemptConfig>) =>
      api.put<RegimeExemptConfig>("/regime-config", v),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["regime-config"] }),
  });
}

export function useToggleAlertConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { alert_type: string; enabled: boolean }) =>
      api.put<{ alert_type: string; enabled: boolean }>(
        `/alert-config/${v.alert_type}`,
        { enabled: v.enabled },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alert-config"] }),
    onError: (err: { message?: string; detail?: { message?: string } }) => {
      toast.error(err.detail?.message || err.message || "Failed to update alert type");
    },
  });
}

/** Bulk-toggle EVERY alert type at once ("All off" / "All on"). */
export function useToggleAllAlertConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { enabled: boolean; category?: string }) =>
      api.put<{ updated: number; enabled: boolean }>("/alert-config", vars),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alert-config"] }),
    onError: (err: { message?: string; detail?: { message?: string } }) => {
      toast.error(err.detail?.message || err.message || "Failed to update alert types");
    },
  });
}
