/** Client-side technical indicator calculations for chart overlays. */

export interface TimeValue {
  time: string | number;
  value: number;
}

/**
 * Simple Moving Average.
 * Returns one value per bar — NaN for the first (period-1) bars.
 */
export function computeSMA(
  closes: { time: string | number; close: number }[],
  period: number,
): TimeValue[] {
  const result: TimeValue[] = [];
  for (let i = 0; i < closes.length; i++) {
    if (i < period - 1) {
      continue; // skip until we have enough bars
    }
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) {
      sum += closes[j].close;
    }
    result.push({ time: closes[i].time, value: sum / period });
  }
  return result;
}

/**
 * Exponential Moving Average.
 */
export function computeEMA(
  closes: { time: string | number; close: number }[],
  period: number,
): TimeValue[] {
  if (closes.length < period) return [];

  const k = 2 / (period + 1);
  const result: TimeValue[] = [];

  // Seed with SMA of first `period` bars
  let sum = 0;
  for (let i = 0; i < period; i++) {
    sum += closes[i].close;
  }
  let ema = sum / period;
  result.push({ time: closes[period - 1].time, value: ema });

  for (let i = period; i < closes.length; i++) {
    ema = closes[i].close * k + ema * (1 - k);
    result.push({ time: closes[i].time, value: ema });
  }
  return result;
}

/**
 * RSI(period) — Wilder's smoothing. Returns one value per bar from `period` on.
 */
export function computeRSI(
  closes: { time: string | number; close: number }[],
  period = 14,
): TimeValue[] {
  if (closes.length <= period) return [];
  const result: TimeValue[] = [];
  let avgGain = 0;
  let avgLoss = 0;
  // Seed: simple average of the first `period` gains/losses.
  for (let i = 1; i <= period; i++) {
    const ch = closes[i].close - closes[i - 1].close;
    if (ch >= 0) avgGain += ch; else avgLoss -= ch;
  }
  avgGain /= period;
  avgLoss /= period;
  const rsiAt = () => (avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss));
  result.push({ time: closes[period].time, value: rsiAt() });
  for (let i = period + 1; i < closes.length; i++) {
    const ch = closes[i].close - closes[i - 1].close;
    const gain = ch >= 0 ? ch : 0;
    const loss = ch < 0 ? -ch : 0;
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    result.push({ time: closes[i].time, value: rsiAt() });
  }
  return result;
}

/**
 * VWAP — anchored to start of data (typically session start for intraday).
 */
export function computeVWAP(
  bars: { time: string | number; high: number; low: number; close: number; volume: number }[],
): TimeValue[] {
  let cumVolume = 0;
  let cumTP = 0;
  const result: TimeValue[] = [];

  for (const bar of bars) {
    const tp = (bar.high + bar.low + bar.close) / 3;
    cumVolume += bar.volume;
    cumTP += tp * bar.volume;
    result.push({
      time: bar.time,
      value: cumVolume > 0 ? cumTP / cumVolume : tp,
    });
  }
  return result;
}
