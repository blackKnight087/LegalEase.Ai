import Link from "next/link";

export default function NotFound() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-8 bg-slate-50">
      <h1 className="text-2xl font-semibold text-navy mb-2">Page not found</h1>
      <p className="text-sm text-slate-600 mb-6">This route does not exist.</p>
      <Link href="/" className="text-sm font-medium text-blue-700 hover:underline">
        Back to LegalEase
      </Link>
    </div>
  );
}
