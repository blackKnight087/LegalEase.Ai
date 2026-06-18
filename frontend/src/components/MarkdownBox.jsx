import ReactMarkdown from "react-markdown";

export default function MarkdownBox({ content, className = "" }) {
  if (!content) return null;
  return (
    <div className={`prose prose-sm max-w-none prose-slate ${className}`}>
      <ReactMarkdown>{content}</ReactMarkdown>
    </div>
  );
}
