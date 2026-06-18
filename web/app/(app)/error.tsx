"use client";

import { formatApiError } from "@/lib/formatApiError";

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-4 sm:p-8 px-6 text-center">
      <h2 className="text-lg font-semibold text-navy mb-2">Could not load this page</h2>
      <p className="text-sm text-slate-600 mb-4 max-w-md text-center">
        {formatApiError(error)}
      </p>
      <button
        type="button"
        onClick={() => reset()}
        className="px-4 py-2 rounded-lg bg-navy text-white text-sm"
      >
        Retry
      </button>
    </div>
  );
}
