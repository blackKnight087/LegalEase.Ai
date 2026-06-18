"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";
import CollaborationHub from "@/components/collaboration/CollaborationHub";

function MatterDiscussionInner() {
  const params = useParams();
  const matterId = String(params.matterId || "");
  return <CollaborationHub matterId={matterId} embedded />;
}

export default function MatterDiscussionPage() {
  return (
    <Suspense fallback={<div className="p-4 text-sm text-slate-500">Loading discussion…</div>}>
      <MatterDiscussionInner />
    </Suspense>
  );
}
