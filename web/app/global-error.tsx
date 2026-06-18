"use client";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen flex flex-col items-center justify-center p-8 bg-slate-50 font-sans">
        <h1 className="text-xl font-semibold text-slate-900 mb-2">Application error</h1>
        <p className="text-sm text-slate-600 mb-6">{error.message}</p>
        <button
          type="button"
          onClick={() => reset()}
          className="px-4 py-2 rounded-lg bg-slate-900 text-white text-sm"
        >
          Reload
        </button>
      </body>
    </html>
  );
}
