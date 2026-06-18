"use client";

import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import MatterIntelligenceStatus from "@/components/matters/MatterIntelligenceStatus";

const MatterTimelinePanel = dynamic(
  () => import("@/components/matters/MatterTimelinePanel"),
  {
    ssr: false,
    loading: () => (
      <p className="text-sm text-slate-500 p-2">Loading timeline…</p>
    ),
  }
);

export default function MatterTimelinePage() {
  const params = useParams();
  const matterId = String(params.matterId || "");
  return (
    <div className="space-y-4 max-w-4xl">
      <MatterIntelligenceStatus matterId={matterId} />
      <MatterTimelinePanel matterId={matterId} />
    </div>
  );
}
