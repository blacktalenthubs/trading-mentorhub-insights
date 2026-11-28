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
 * 30-week SMA (Weinstein) over daily or weekly bars, drawn as a stepped
 * line: bars are grouped into calendar weeks (Mon-start, UTC) and each bar
 * takes the mean of the last 30 weekly closes, its own week's latest close
 * included (the forming week counts, like TradingView). On weekly bars it
 * degenerates to a plain SMA(30). Needs 30 weeks of bars before the first
 * value, so intraday fetches (a few days) draw nothing.
 */
export function computeSMA30W(
  closes: { time: string | number; close: number }[],
): TimeValue[] {
  const weekKey = (t: string | number): string => {
    const d =
      typeof t === "number"
        ? new Date(t * 1000)
        : new Date(`${String(t).slice(0, 10)}T00:00:00Z`);
    if (isNaN(+d)) return String(t);
    const dow = (d.getUTCDay() + 6) % 7; // Mon=0
    const mon = new Date(
      Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() - dow),
    );
    return mon.toISOString().slice(0, 10);
  };
  const weekCloses: number[] = [];
  const barWeekIdx: number[] = [];
  let curKey: string | null = null;
  for (const b of closes) {
    const k = weekKey(b.time);
    if (k !== curKey) {
      weekCloses.push(b.close);
      curKey = k;
    } else {
      weekCloses[weekCloses.length - 1] = b.close;
    }
    barWeekIdx.push(weekCloses.length - 1);
  }
  const result: TimeValue[] = [];
  for (let i = 0; i < closes.length; i++) {
    const w = barWeekIdx[i];
    if (w < 29) continue;
    let sum = 0;
    for (let j = w - 29; j <= w; j++) sum += weekCloses[j];
    result.push({ time: closes[i].time, value: sum / 30 });
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
