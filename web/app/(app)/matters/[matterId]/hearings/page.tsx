"use client";

import { useParams } from "next/navigation";
import MatterHearingsPanel from "@/components/matters/MatterHearingsPanel";
import MatterIntelligenceStatus from "@/components/matters/MatterIntelligenceStatus";

export default function MatterHearingsPage() {
  const params = useParams();
  const matterId = String(params.matterId || "");
  return (
    <div className="space-y-4">
      <MatterIntelligenceStatus matterId={matterId} />
      <MatterHearingsPanel matterId={matterId} />
    </div>
  );
}
