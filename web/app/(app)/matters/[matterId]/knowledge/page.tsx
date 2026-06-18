"use client";

import { useParams } from "next/navigation";
import MatterKnowledgePanel from "@/components/matters/MatterKnowledgePanel";
import MatterIntelligenceStatus from "@/components/matters/MatterIntelligenceStatus";

export default function MatterKnowledgePage() {
  const params = useParams();
  const matterId = String(params.matterId || "");
  return (
    <div className="space-y-4 max-w-4xl">
      <MatterIntelligenceStatus matterId={matterId} />
      <MatterKnowledgePanel matterId={matterId} />
    </div>
  );
}
