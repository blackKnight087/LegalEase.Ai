export default function PrivacyPolicyPage() {
  return (
    <div className="min-h-screen bg-slate-50 p-8">
      <article className="max-w-2xl mx-auto bg-white border rounded-2xl p-8 prose prose-slate">
        <h1>Privacy Policy</h1>
        <p className="text-sm text-slate-500">Last updated: May 2026</p>
        <p>
          LegalEase processes documents and chat data you upload to provide legal research and
          case workspace features. Data is stored on infrastructure you control when self-hosted,
          or on servers operated by your deployment provider.
        </p>
        <h2>Data we process</h2>
        <ul>
          <li>Account credentials and profile settings</li>
          <li>Uploaded documents, chat history, and matter workspaces</li>
          <li>Usage logs for security and product improvement</li>
        </ul>
        <h2>Your rights</h2>
        <p>
          You may export or delete your account from Settings. Deletion permanently removes your
          chat history, documents metadata, indexes, and profile from this deployment.
        </p>
        <h2>Contact</h2>
        <p>For privacy requests, contact your firm administrator or deployment operator.</p>
      </article>
    </div>
  );
}
