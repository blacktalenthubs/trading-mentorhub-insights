/**
 * Premium Desk — trade detail route (/premium-desk/:sym).
 *
 * On desktop the sizing panel lives beside the feed; this route is the mobile / deep-link
 * surface for a single candidate. It just hosts the shared PremiumTradePanel. READ-ONLY.
 */
import { useParams } from "react-router-dom";

import PremiumTradePanel from "../components/PremiumTradePanel";

export default function PremiumDeskDetailPage() {
  const { sym = "" } = useParams();
  return (
    <div className="h-full overflow-y-auto bg-surface-0">
      <PremiumTradePanel sym={sym} variant="page" />
    </div>
  );
}
