"use client";

import { useParams } from "next/navigation";
import MatterAIPanel from "@/components/matters/MatterAIPanel";
import MatterIntelligenceStatus from "@/components/matters/MatterIntelligenceStatus";

export default function MatterAiPage() {
  const params = useParams();
  const matterId = String(params.matterId || "");
  return (
    <div className="space-y-4 max-w-4xl">
      <MatterIntelligenceStatus matterId={matterId} />
      <MatterAIPanel matterId={matterId} />
    </div>
  );
}
