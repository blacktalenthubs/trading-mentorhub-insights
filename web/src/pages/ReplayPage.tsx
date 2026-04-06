/** Public Replay Page — shareable trade replay at /replay/:alertId.
 *
 *  Opens in full-screen studio mode. No auth required for viewing.
 *  Used for social media sharing and content creation.
 */

import { useParams, useNavigate } from "react-router-dom";
import ChartReplay from "../components/ChartReplay";

export default function ReplayPage() {
  const { alertId } = useParams();
  const navigate = useNavigate();
  const id = parseInt(alertId || "0", 10);

  if (!id) {
    return (
      <div className="min-h-screen bg-surface-0 flex items-center justify-center">
        <p className="text-text-muted">Invalid replay link</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-surface-0">
      <ChartReplay alertId={id} onClose={() => navigate("/")} />
    </div>
  );
}
