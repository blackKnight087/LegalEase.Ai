"use client";

import { Suspense } from "react";
import CollaborationHub from "@/components/collaboration/CollaborationHub";

export default function CollaborationPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center flex-1 text-slate-500 text-sm">
          Loading Firm Chat…
        </div>
      }
    >
      <div className="flex flex-col flex-1 min-h-0 h-[calc(100dvh-3.5rem)] lg:h-[calc(100dvh-1px)] px-3 pb-2 pt-2 lg:px-6 lg:pt-4 lg:pb-4">
        <CollaborationHub />
      </div>
    </Suspense>
  );
}
