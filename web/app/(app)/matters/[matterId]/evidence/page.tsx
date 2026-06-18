"use client";

import { useParams } from "next/navigation";
import MatterEvidencePanel from "@/components/matters/MatterEvidencePanel";
import MatterIntelligenceStatus from "@/components/matters/MatterIntelligenceStatus";

export default function MatterEvidencePage() {
  const params = useParams();
  const matterId = String(params.matterId || "");
  return (
    <div className="space-y-4 max-w-4xl">
      <MatterIntelligenceStatus matterId={matterId} />
      <MatterEvidencePanel matterId={matterId} />
    </div>
  );
}
