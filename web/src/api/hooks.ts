/** TanStack Query hooks for all API endpoints. */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { AuthTokens, SignalResult, Alert, User } from "../types";

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
}

export function useWatchlist() {
  return useQuery({
    queryKey: ["watchlist"],
    queryFn: () => api.get<WatchlistItem[]>("/watchlist"),
  });
}

export function useAddSymbol() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbol: string) => api.post<WatchlistItem>("/watchlist", { symbol }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });
}

export function useRemoveSymbol() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbol: string) => api.delete(`/watchlist/${symbol}`),
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
    staleTime: 5 * 60_000,
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

// --- Alerts ---

export function useAlertsToday() {
  return useQuery({
    queryKey: ["alerts-today"],
    queryFn: () => api.get<Alert[]>("/alerts/today"),
    refetchInterval: 60_000,
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
    onSuccess: (_, vars) => qc.invalidateQueries({ queryKey: ["chart-levels", vars.symbol] }),
  });
}

export function useDeleteChartLevel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, symbol }: { id: number; symbol: string }) =>
      api.delete(`/charts/levels/${id}`),
    onSuccess: (_, vars) => qc.invalidateQueries({ queryKey: ["chart-levels", vars.symbol] }),
  });
}

export function useOHLCV(symbol: string, period = "3mo") {
  return useQuery({
    queryKey: ["ohlcv", symbol, period],
    queryFn: () => api.get<OHLCBar[]>(`/charts/ohlcv/${symbol}?period=${period}`),
    enabled: !!symbol,
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

export function useOpenTrades() {
  return useQuery({
    queryKey: ["real-trades-open"],
    queryFn: () => api.get<RealTrade[]>("/real-trades/open"),
  });
}

export function useClosedTrades(limit = 50) {
  return useQuery({
    queryKey: ["real-trades-closed", limit],
    queryFn: () => api.get<RealTrade[]>(`/real-trades/closed?limit=${limit}`),
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

export function useRunBacktest() {
  return useMutation({
    mutationFn: (body: { symbols: string[]; start_date: string; end_date: string }) =>
      api.post<BacktestResult[]>("/backtest/run", body),
  });
}
