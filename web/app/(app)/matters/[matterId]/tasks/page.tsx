"use client";

import { useParams } from "next/navigation";
import MatterDashboard from "@/components/matters/MatterDashboard";

export default function MatterTasksPage() {
  const params = useParams();
  return <MatterDashboard matterId={String(params.matterId)} initialTab="tasks" />;
}
