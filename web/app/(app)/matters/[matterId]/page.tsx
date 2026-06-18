"use client";

import { useParams } from "next/navigation";
import MatterDashboard from "@/components/matters/MatterDashboard";

export default function MatterOverviewPage() {
  const params = useParams();
  const matterId = String(params.matterId || "");
  return (
    <MatterDashboard matterId={matterId} initialTab="overview" />
  );
}
