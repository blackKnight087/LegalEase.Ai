"use client";

export default function RootError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-8 bg-slate-50">
      <h1 className="text-xl font-semibold text-navy mb-2">Something went wrong</h1>
      <p className="text-sm text-slate-600 mb-6 max-w-md text-center">
        {error.message || "An unexpected error occurred."}
      </p>
      <button
        type="button"
        onClick={() => reset()}
        className="px-4 py-2 rounded-lg bg-navy text-white text-sm font-medium"
      >
        Try again
      </button>
    </div>
  );
}
