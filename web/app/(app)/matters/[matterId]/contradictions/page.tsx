"use client";

import { useParams } from "next/navigation";
import ContradictionPanel from "@/components/matters/ContradictionPanel";
import MatterIntelligenceStatus from "@/components/matters/MatterIntelligenceStatus";

export default function MatterContradictionsPage() {
  const params = useParams();
  const matterId = String(params.matterId || "");
  return (
    <div className="space-y-4 max-w-4xl">
      <MatterIntelligenceStatus matterId={matterId} />
      <ContradictionPanel matterId={matterId} />
    </div>
  );
}
