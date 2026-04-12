/** Attribution tracking — capture UTM params and referrer on first landing,
 *  persist to localStorage, and attach to registration requests.
 *
 *  Flow:
 *    1. App mount -> captureAttribution() reads ?utm_* from URL + document.referrer
 *    2. First-touch attribution wins — only write if not already stored
 *    3. getAttribution() returns the stored data for register request
 *    4. Optional clearAttribution() after successful signup
 */

const STORAGE_KEY = "tcp_attribution_v1";
const EXPIRY_DAYS = 30;

export interface Attribution {
  utm_source?: string;
  utm_medium?: string;
  utm_campaign?: string;
  referrer?: string;
  captured_at: number; // unix ms
}

/** Run on every app mount. First-touch wins — won't overwrite existing attribution. */
export function captureAttribution(): void {
  try {
    // Skip if we already have fresh attribution
    const existing = readRaw();
    if (existing && !isExpired(existing)) {
      return;
    }

    const params = new URLSearchParams(window.location.search);
    const utm_source = params.get("utm_source") || undefined;
    const utm_medium = params.get("utm_medium") || undefined;
    const utm_campaign = params.get("utm_campaign") || undefined;
    const referrer = document.referrer || undefined;

    // Only store if we got ANY signal (direct visits with no UTM/referrer = skip)
    if (!utm_source && !utm_medium && !utm_campaign && !referrer) {
      return;
    }

    const data: Attribution = {
      utm_source: clip(utm_source, 100),
      utm_medium: clip(utm_medium, 100),
      utm_campaign: clip(utm_campaign, 200),
      referrer: clip(referrer, 500),
      captured_at: Date.now(),
    };

    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch {
    // localStorage unavailable (SSR / private mode) — ignore
  }
}

/** Return stored attribution or null if missing/expired. */
export function getAttribution(): Attribution | null {
  const raw = readRaw();
  if (!raw || isExpired(raw)) return null;
  return raw;
}

/** Clear after successful use (optional — safe to leave for repeat analytics). */
export function clearAttribution(): void {
  try { localStorage.removeItem(STORAGE_KEY); } catch { /* empty */ }
}

function readRaw(): Attribution | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as Attribution;
  } catch {
    return null;
  }
}

function isExpired(a: Attribution): boolean {
  const age_ms = Date.now() - (a.captured_at || 0);
  return age_ms > EXPIRY_DAYS * 24 * 60 * 60 * 1000;
}

function clip(v: string | undefined, max: number): string | undefined {
  if (!v) return undefined;
  return v.slice(0, max);
}
