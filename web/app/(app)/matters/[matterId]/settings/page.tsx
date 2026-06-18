"use client";

import { useParams, useRouter } from "next/navigation";
import MatterSettingsForm from "@/components/matters/MatterSettingsForm";

export default function MatterSettingsPage() {
  const params = useParams();
  const router = useRouter();
  const matterId = String(params.matterId || "");

  return (
    <MatterSettingsForm
      matterId={matterId}
      onDeleted={() => router.push("/matters")}
    />
  );
}
