import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import * as api from "../api/client.js";
import PageHeader from "../components/PageHeader.jsx";
import MetricCard from "../components/MetricCard.jsx";

export default function DashboardPage() {
  const [data, setData] = useState(null);

  useEffect(() => {
    api.fetchDashboardFull().then(setData).catch(() => {});
  }, []);

  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle={data ? `Welcome back, ${data.username}` : "Loading…"}
      />
      <div className="flex-1 overflow-y-auto le-scroll p-8">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <MetricCard icon="📄" label="Documents" value={data?.documents ?? "—"} />
          <MetricCard icon="💬" label="AI Queries" value={data?.queries ?? "—"} />
          <MetricCard icon="🧩" label="KB Chunks" value={data?.kb_chunks ?? "—"} />
          <MetricCard icon="🤖" label="LLM" value={data?.llm_online ? "✅" : "❌"} />
        </div>

        <h2 className="font-serif text-lg font-bold text-navy mb-3">Quick Actions</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
          {[
            { to: "/", label: "💬 Ask AI" },
            { to: "/documents", label: "📤 Upload Docs" },
            { to: "/drafting", label: "📝 Draft Document" },
            { to: "/tools", label: "🔧 Legal Tools" },
          ].map((a) => (
            <Link
              key={a.to}
              to={a.to}
              className="bg-white border border-slate-200 rounded-xl py-3 text-center text-sm font-semibold hover:border-navy hover:shadow-sm transition-all"
            >
              {a.label}
            </Link>
          ))}
        </div>

        <div className="grid md:grid-cols-2 gap-6">
          <div className="bg-white rounded-2xl border border-slate-200/80 p-5">
            <h3 className="font-semibold text-navy mb-3">Recent Queries</h3>
            {(data?.recent_queries || []).length ? (
              <ul className="space-y-3">
                {data.recent_queries.map((q, i) => (
                  <li key={i} className="text-sm border-b border-slate-100 pb-2 last:border-0">
                    <p className="font-medium text-slate-800 truncate">{q.question}</p>
                    <p className="text-slate-500 text-xs mt-1 line-clamp-2">{q.answer}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-slate-400">No queries yet.</p>
            )}
          </div>
          <div className="bg-white rounded-2xl border border-slate-200/80 p-5">
            <h3 className="font-semibold text-navy mb-3">Recent Documents</h3>
            {(data?.recent_documents || []).length ? (
              <ul className="space-y-2 text-sm">
                {data.recent_documents.map((d, i) => (
                  <li key={i} className="flex justify-between text-slate-700">
                    <span className="truncate">📄 {d.filename}</span>
                    <span className="text-slate-400 shrink-0 ml-2">{d.pages} pg</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-slate-400">No documents uploaded.</p>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
