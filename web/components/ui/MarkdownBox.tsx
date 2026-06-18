import ReactMarkdown from "react-markdown";

export default function MarkdownBox({
  content,
  className = "",
}: {
  content: string;
  className?: string;
}) {
  if (!content) return null;
  return (
    <div className={`prose prose-sm max-w-none prose-slate ${className}`}>
      <ReactMarkdown>{content}</ReactMarkdown>
    </div>
  );
}
