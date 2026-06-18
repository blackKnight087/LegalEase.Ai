"use client";

import { useParams } from "next/navigation";
import MatterChatHistory from "@/components/matters/MatterChatHistory";

export default function MatterHistoryPage() {
  const params = useParams();
  const matterId = String(params.matterId || "");
  return (
    <div className="max-w-2xl">
      <h2 className="text-lg font-semibold text-navy m-0 mb-4">Chat history</h2>
      <MatterChatHistory matterId={matterId} />
    </div>
  );
}
