"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Underline from "@tiptap/extension-underline";
import TextAlign from "@tiptap/extension-text-align";
import Placeholder from "@tiptap/extension-placeholder";
import Table from "@tiptap/extension-table";
import TableRow from "@tiptap/extension-table-row";
import TableCell from "@tiptap/extension-table-cell";
import TableHeader from "@tiptap/extension-table-header";
import TextStyle from "@tiptap/extension-text-style";
import FontFamily from "@tiptap/extension-font-family";
import { FontSize } from "@/lib/tiptapFontSize";
import { markdownToHtml, normalizeContent } from "@/lib/legalDocumentFormat";
import type { OutlineSection } from "@/lib/legalDocumentFormat";
import { countWordsFromHtml } from "@/lib/legalDocumentTemplates";
import { splitHtmlIntoPages } from "@/lib/legalPageSplit";

export type LegalDocumentEditorHandle = {
  insertHtml: (html: string) => void;
  scrollToSection: (id: string) => void;
  getSelectedText: () => string;
  focus: () => void;
};

type Props = {
  content: string;
  contentFormat?: string;
  onChange: (html: string) => void;
  onOutlineChange?: (sections: OutlineSection[]) => void;
  onStatsChange?: (stats: { words: number; pages: number }) => void;
  onSelectionChange?: (text: string) => void;
  editable?: boolean;
  documentTitle?: string;
  headerText?: string;
  footerText?: string;
  onHeaderChange?: (t: string) => void;
  onFooterChange?: (t: string) => void;
};

const FONT_FAMILIES = [
  { label: "Times New Roman", value: "Times New Roman, Times, serif" },
  { label: "Book Antiqua", value: "Book Antiqua, Palatino, serif" },
  { label: "Arial", value: "Arial, Helvetica, sans-serif" },
  { label: "Calibri", value: "Calibri, sans-serif" },
];

const FONT_SIZES = ["10pt", "11pt", "12pt", "13pt", "14pt", "16pt", "18pt"];
const LINE_HEIGHTS = ["1.15", "1.5", "1.75", "2"];

function ToolbarButton({
  onClick,
  active,
  title,
  children,
  disabled,
}: {
  onClick: () => void;
  active?: boolean;
  title: string;
  children: React.ReactNode;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={`drafting-tb-btn disabled:opacity-40 ${active ? "is-active" : ""}`}
    >
      {children}
    </button>
  );
}

function extractOutline(html: string): OutlineSection[] {
  if (typeof DOMParser === "undefined") return [];
  const doc = new DOMParser().parseFromString(html || "<p></p>", "text/html");
  const sections: OutlineSection[] = [];
  doc.querySelectorAll("h1, h2, h3").forEach((el, idx) => {
    const tag = el.tagName.toLowerCase();
    const level = tag === "h1" ? 1 : tag === "h2" ? 2 : 3;
    const title = (el.textContent || "").trim() || `Section ${idx + 1}`;
    sections.push({ id: `outline-${idx}`, level, title });
  });
  return sections;
}

const LegalDocumentEditor = forwardRef<LegalDocumentEditorHandle, Props>(function LegalDocumentEditor(
  {
    content,
    contentFormat = "markdown",
    onChange,
    onOutlineChange,
    onStatsChange,
    onSelectionChange,
    editable = true,
    documentTitle = "",
    headerText = "",
    footerText = "",
    onHeaderChange,
    onFooterChange,
  },
  ref
) {
  const pageRef = useRef<HTMLDivElement>(null);
  const [lineHeight, setLineHeight] = useState("1.5");
  const [editChrome, setEditChrome] = useState(false);
  const { html: initial } = normalizeContent(content, contentFormat);

  const emitStats = useCallback(
    (html: string) => {
      const words = countWordsFromHtml(html);
      onStatsChange?.({ words, pages: Math.max(1, Math.ceil(words / 350)) });
    },
    [onStatsChange]
  );

  const editor = useEditor({
    extensions: [
      StarterKit.configure({ heading: { levels: [1, 2, 3] } }),
      Underline,
      TextStyle,
      FontSize,
      FontFamily,
      TextAlign.configure({ types: ["heading", "paragraph"] }),
      Placeholder.configure({ placeholder: "Begin drafting — use Templates for firm structure…" }),
      Table.configure({ resizable: true }),
      TableRow,
      TableHeader,
      TableCell,
    ],
    content: initial,
    editable,
    onUpdate: ({ editor: ed }) => {
      const html = ed.getHTML();
      onChange(html);
      onOutlineChange?.(extractOutline(html));
      emitStats(html);
    },
    onSelectionUpdate: ({ editor: ed }) => {
      const { from, to } = ed.state.selection;
      if (from === to) {
        onSelectionChange?.("");
        return;
      }
      onSelectionChange?.(ed.state.doc.textBetween(from, to, " "));
    },
    editorProps: {
      attributes: {
        class: "legal-editor-body focus:outline-none",
        style: `line-height: ${lineHeight}`,
      },
    },
  });

  useImperativeHandle(ref, () => ({
    insertHtml: (html: string) => {
      editor?.chain().focus().insertContent(html).run();
    },
    scrollToSection: (id: string) => {
      const root = pageRef.current;
      if (!root) return;
      const headings = root.querySelectorAll("h1, h2, h3");
      const idx = parseInt(id.replace("outline-", ""), 10);
      const el = headings[idx] as HTMLElement | undefined;
      el?.scrollIntoView({ behavior: "smooth", block: "start" });
    },
    getSelectedText: () => {
      if (!editor) return "";
      const { from, to } = editor.state.selection;
      if (from === to) return "";
      return editor.state.doc.textBetween(from, to, " ");
    },
    focus: () => editor?.chain().focus().run(),
  }));

  useEffect(() => {
    if (!editor) return;
    const incoming = normalizeContent(content, contentFormat).html;
    const current = editor.getHTML();
    if (incoming && incoming !== current) {
      editor.commands.setContent(incoming, false);
      onOutlineChange?.(extractOutline(incoming));
      emitStats(incoming);
    }
  }, [content, contentFormat, editor, onOutlineChange, emitStats]);

  useEffect(() => {
    if (!editor) return;
    const html = editor.getHTML();
    onOutlineChange?.(extractOutline(html));
    emitStats(html);
  }, [editor, onOutlineChange, emitStats]);

  useEffect(() => {
    if (!editor) return;
    const el = editor.view.dom as HTMLElement;
    el.style.lineHeight = lineHeight;
  }, [editor, lineHeight]);

  const setFontSize = (size: string) => {
    editor?.chain().focus().setMark("textStyle", { fontSize: size }).run();
  };

  const paragraphIndent = (dir: "in" | "out") => {
    if (!editor) return;
    const step = dir === "in" ? "+=2em" : "-=2em";
    editor.chain().focus().setMark("textStyle", {}).run();
    const el = editor.view.dom as HTMLElement;
    const p = window.getSelection()?.anchorNode?.parentElement?.closest("p");
    if (p) {
      const cur = parseFloat(p.style.marginLeft || "0") || 0;
      p.style.marginLeft = dir === "in" ? `${cur + 24}px` : `${Math.max(0, cur - 24)}px`;
    } else {
      void step;
    }
  };

  const insertPageBreak = useCallback(() => {
    editor?.chain().focus().insertContent('<hr data-page-break="true" />').run();
  }, [editor]);

  const insertFootnote = useCallback(() => {
    editor
      ?.chain()
      .focus()
      .insertContent('<sup class="legal-footnote">[FN: cite source]</sup>')
      .run();
  }, [editor]);

  if (!editor) {
    return (
      <div className="legal-a4-canvas flex-1 flex items-center justify-center">
        <div className="legal-a4-page h-[70vh] w-full max-w-[210mm] bg-white animate-pulse rounded-sm shadow-lg" />
      </div>
    );
  }

  return (
    <div className="flex flex-col flex-1 min-h-0 overflow-hidden rounded-xl border border-slate-300/80 shadow-lg">
      <div className="border-b bg-white sticky top-0 z-20 shadow-sm">
        <div className="drafting-format-toolbar">
          <select
            className="text-xs border rounded px-1 py-1 max-w-[120px]"
            title="Font"
            onChange={(e) => editor.chain().focus().setFontFamily(e.target.value).run()}
            defaultValue="Times New Roman, Times, serif"
          >
            {FONT_FAMILIES.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
          <select
            className="text-xs border rounded px-1 py-1 w-16"
            title="Font size"
            onChange={(e) => setFontSize(e.target.value)}
            defaultValue="12pt"
          >
            {FONT_SIZES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <select
            className="text-xs border rounded px-1 py-1 w-14"
            title="Line spacing"
            value={lineHeight}
            onChange={(e) => setLineHeight(e.target.value)}
          >
            {LINE_HEIGHTS.map((h) => (
              <option key={h} value={h}>
                {h}
              </option>
            ))}
          </select>
          <span className="w-px h-6 bg-slate-300 mx-0.5" />
          <ToolbarButton title="Bold" active={editor.isActive("bold")} onClick={() => editor.chain().focus().toggleBold().run()}>
            B
          </ToolbarButton>
          <ToolbarButton title="Italic" active={editor.isActive("italic")} onClick={() => editor.chain().focus().toggleItalic().run()}>
            I
          </ToolbarButton>
          <ToolbarButton title="Underline" active={editor.isActive("underline")} onClick={() => editor.chain().focus().toggleUnderline().run()}>
            U
          </ToolbarButton>
          <span className="w-px h-6 bg-slate-300 mx-0.5" />
          <ToolbarButton title="H1" active={editor.isActive("heading", { level: 1 })} onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}>
            H1
          </ToolbarButton>
          <ToolbarButton title="H2" active={editor.isActive("heading", { level: 2 })} onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}>
            H2
          </ToolbarButton>
          <ToolbarButton title="H3" active={editor.isActive("heading", { level: 3 })} onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}>
            H3
          </ToolbarButton>
          <span className="w-px h-6 bg-slate-300 mx-0.5" />
          <ToolbarButton title="Bullets" active={editor.isActive("bulletList")} onClick={() => editor.chain().focus().toggleBulletList().run()}>
            •
          </ToolbarButton>
          <ToolbarButton title="Numbered" active={editor.isActive("orderedList")} onClick={() => editor.chain().focus().toggleOrderedList().run()}>
            1.
          </ToolbarButton>
          <ToolbarButton title="Paragraph indent" onClick={() => paragraphIndent("in")}>
            →|
          </ToolbarButton>
          <ToolbarButton title="Paragraph outdent" onClick={() => paragraphIndent("out")}>
            |←
          </ToolbarButton>
          <ToolbarButton title="Table" onClick={() => editor.chain().focus().insertTable({ rows: 4, cols: 4, withHeaderRow: true }).run()}>
            ⊞
          </ToolbarButton>
          <ToolbarButton title="Page break" onClick={insertPageBreak}>
            Page ↵
          </ToolbarButton>
          <ToolbarButton title="Footnote marker" onClick={insertFootnote}>
            FN
          </ToolbarButton>
          <span className="w-px h-6 bg-slate-300 mx-0.5" />
          <ToolbarButton title="Left" onClick={() => editor.chain().focus().setTextAlign("left").run()}>
            ⬅
          </ToolbarButton>
          <ToolbarButton title="Center" onClick={() => editor.chain().focus().setTextAlign("center").run()}>
            ↔
          </ToolbarButton>
          <ToolbarButton title="Right" onClick={() => editor.chain().focus().setTextAlign("right").run()}>
            ➡
          </ToolbarButton>
          <ToolbarButton title="Justify" onClick={() => editor.chain().focus().setTextAlign("justify").run()}>
            ≡
          </ToolbarButton>
          <button
            type="button"
            title="Edit header/footer"
            onClick={() => setEditChrome((v) => !v)}
            className={`ml-auto px-2 py-1 text-xs rounded border ${editChrome ? "bg-navy text-white" : "bg-white"}`}
          >
            Header/Footer
          </button>
        </div>
      </div>

      <div className="legal-ruler-wrap shrink-0">
        <div className="legal-ruler mx-auto" aria-hidden>
          {Array.from({ length: 18 }).map((_, i) => (
            <span key={i} className="legal-ruler-tick">
              {i * 10}
            </span>
          ))}
        </div>
      </div>

      <div className="legal-a4-canvas flex-1 overflow-y-auto le-scroll py-6 px-4 space-y-4">
        {(() => {
          const pageParts = splitHtmlIntoPages(editor.getHTML());
          const pageCount = Math.max(1, pageParts.length);
          return (
            <>
              <div ref={pageRef} className="legal-a4-page mx-auto legal-page-shadow">
                {editChrome ? (
                  <div className="legal-page-header legal-page-header-editable">
                    <input
                      className="legal-header-input"
                      value={headerText || documentTitle}
                      onChange={(e) => onHeaderChange?.(e.target.value)}
                      placeholder="Header — firm name, matter ref"
                    />
                    <input
                      className="legal-header-input text-right max-w-[40%]"
                      value={footerText || "Confidential · Draft"}
                      onChange={(e) => onFooterChange?.(e.target.value)}
                      placeholder="Header right"
                    />
                  </div>
                ) : (
                  <div className="legal-page-header">
                    <span className="legal-page-header-title">{headerText || documentTitle || "Untitled"}</span>
                    <span className="legal-page-header-meta">{footerText || "Confidential · Draft"}</span>
                  </div>
                )}
                <div className="legal-page-body" style={{ lineHeight }}>
                  <EditorContent editor={editor} />
                </div>
                <div className="legal-page-footer">
                  <span>{headerText ? `${headerText} · LegalEase` : "LegalEase Drafting Studio"}</span>
                  <span className="legal-page-num">
                    {pageCount > 1 ? `${pageCount} pages (use Page ↵ for breaks)` : "Page 1 · Draft"}
                  </span>
                </div>
              </div>
              {pageCount > 1 &&
                pageParts.slice(1).map((html, i) => (
                  <div
                    key={i}
                    className="legal-a4-page mx-auto legal-page-shadow opacity-90 scale-[0.98] pointer-events-none"
                    aria-hidden
                  >
                    <div className="legal-page-header">
                      <span className="legal-page-header-meta">Continued</span>
                    </div>
                    <div
                      className="legal-page-body legal-editor-body prose prose-sm"
                      dangerouslySetInnerHTML={{ __html: html }}
                    />
                    <div className="legal-page-footer">
                      <span className="legal-page-num">Page {i + 2} of {pageCount}</span>
                    </div>
                  </div>
                ))}
            </>
          );
        })()}
      </div>
    </div>
  );
});

export default LegalDocumentEditor;
export { markdownToHtml };
