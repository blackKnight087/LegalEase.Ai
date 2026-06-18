import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";

function UserBubble({ content }) {
  return (
    <div className="flex flex-row justify-start w-full">
      <div className="max-w-[65%] bg-gradient-to-br from-[#0f172a] to-[#1e3a8a] text-white rounded-2xl rounded-tl-sm p-4 shadow-sm font-sans text-[0.95rem] leading-relaxed">
        <p className="m-0 whitespace-pre-wrap">{content}</p>
      </div>
    </div>
  );
}

function AssistantCard({ content, sources }) {
  return (
    <div className="flex flex-row justify-end w-full">
      <div className="max-w-[70%] bg-white text-[#1e293b] rounded-2xl rounded-tr-sm p-5 border border-amber-500/25 shadow-md hover:shadow-lg transition-all duration-300 ease-in-out font-sans text-[0.94rem] leading-relaxed">
        <div className="text-[0.72rem] text-amber-600 font-bold tracking-wide mb-2">
          LEGALEASE CORE INTEL
        </div>
        <div className="prose prose-sm max-w-none prose-slate">
          <ReactMarkdown>{content}</ReactMarkdown>
        </div>
        {sources && (
          <p className="mt-3 text-[0.76rem] text-slate-500 border-t border-slate-100 pt-2">
            {sources}
          </p>
        )}
      </div>
    </div>
  );
}

function Hero() {
  return (
    <div className="flex flex-col items-center justify-center text-center py-16 px-4 my-auto">
      <h3 className="font-serif text-3xl font-bold text-navy m-0 mb-3">
        Active Legal Intelligence Engine
      </h3>
      <p className="text-slate-500 max-w-lg text-[0.95rem] leading-relaxed m-0">
        Query statutory provisions, synthesize evidence from your documents, or research
        live Indian law with cited sources.
      </p>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="flex flex-row justify-end w-full">
      <div className="w-72 h-14 rounded-2xl bg-gradient-to-r from-slate-100 via-slate-200 to-slate-100 animate-pulse" />
    </div>
  );
}

export default function ChatViewport({ messages, loading }) {
  const ref = useRef(null);

  useEffect(() => {
    const el = ref.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, loading]);

  return (
    <div
      ref={ref}
      className="flex-1 overflow-y-auto px-8 py-4 flex flex-col gap-6 le-scroll min-h-0"
    >
      {messages.length === 0 && !loading && <Hero />}
      {messages.map((m, i) =>
        m.role === "user" ? (
          <UserBubble key={i} content={m.content} />
        ) : (
          <AssistantCard key={i} content={m.content} sources={m.sourcesLabel} />
        )
      )}
      {loading && <Skeleton />}
    </div>
  );
}
