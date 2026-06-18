export default function TermsOfServicePage() {
  return (
    <div className="min-h-screen bg-slate-50 p-8">
      <article className="max-w-2xl mx-auto bg-white border rounded-2xl p-8 prose prose-slate">
        <h1>Terms of Service</h1>
        <p className="text-sm text-slate-500">Last updated: May 2026</p>
        <p>
          By using LegalEase you agree to use the service for lawful professional purposes. The
          product provides AI-assisted research and is not a substitute for qualified legal
          advice.
        </p>
        <h2>Acceptable use</h2>
        <ul>
          <li>Do not upload unlawful content or material you lack rights to process</li>
          <li>Maintain confidentiality obligations for client matters</li>
          <li>Verify AI outputs before relying on them in filings or advice</li>
        </ul>
        <h2>Subscriptions</h2>
        <p>
          Paid plans are billed according to your Stripe subscription. You may cancel via the
          billing portal linked from Settings.
        </p>
        <h2>Limitation of liability</h2>
        <p>
          The service is provided as-is to the extent permitted by applicable law. Operators may
          update these terms with notice on this page.
        </p>
      </article>
    </div>
  );
}
