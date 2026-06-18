"use client";

import { useParams } from "next/navigation";
import MatterEntitiesPanel from "@/components/matters/MatterEntitiesPanel";
import MatterIntelligenceStatus from "@/components/matters/MatterIntelligenceStatus";

export default function MatterEntitiesPage() {
  const params = useParams();
  const matterId = String(params.matterId || "");
  return (
    <div className="space-y-4 max-w-4xl">
      <MatterIntelligenceStatus matterId={matterId} />
      <MatterEntitiesPanel matterId={matterId} />
    </div>
  );
}
