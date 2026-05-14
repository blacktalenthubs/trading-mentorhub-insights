/** Public Track Record at /track-record
 *
 *  Replaced 2026-05-14: was the AI auto-pilot account view, now serves
 *  the EOD alert report. PublicEODReportPage handles all the rendering;
 *  it detects the base path ("/track-record" vs "/public/eod-report")
 *  from useLocation() so date / symbol routing works consistently.
 *
 *  Both /track-record and /public/eod-report show the same content.
 *  The route exists at /track-record because that's the public-facing
 *  URL linked from the landing page hero.
 */

import PublicEODReportPage from "./PublicEODReportPage";

export default function TrackRecordPage() {
  return <PublicEODReportPage />;
}
