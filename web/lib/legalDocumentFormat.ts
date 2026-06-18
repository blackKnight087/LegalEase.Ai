/** Client-side legal document HTML — strips markdown tables from drafts. */

export const EXECUTION_BLOCK_HTML = `
<h2>EXECUTION</h2>
<p>IN WITNESS WHEREOF the parties have executed this Agreement on the date written below.</p>
<table class="legal-signature-table">
<thead><tr><th>Party</th><th>Name</th><th>Signature</th><th>Date</th></tr></thead>
<tbody>
<tr><td><strong>Party A</strong></td><td></td><td></td><td></td></tr>
<tr><td><strong>Party B</strong></td><td></td><td></td><td></td></tr>
</tbody>
</table>
<h3>Witnesses</h3>
<table class="legal-signature-table">
<thead><tr><th>Witness</th><th>Name</th><th>Signature</th><th>Date</th></tr></thead>
<tbody>
<tr><td>Witness 1</td><td></td><td></td><td></td></tr>
<tr><td>Witness 2</td><td></td><td></td><td></td></tr>
</tbody>
</table>
`;

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function isMdTableRow(line: string): boolean {
  const s = line.trim();
  return Boolean(s) && s.startsWith("|") && s.endsWith("|") && s.includes("|");
}

function mdTableLinesToHtml(lines: string[]): string {
  const rows: string[][] = [];
  for (const line of lines) {
    const s = line.trim();
    if (/^\|[-:\s|]+\|$/.test(s)) continue;
    rows.push(s.slice(1, -1).split("|").map((c) => c.trim()));
  }
  if (!rows.length) return "";
  const [head, ...body] = rows;
  let html = "<table class='legal-signature-table'><thead><tr>";
  for (const c of head) html += `<th>${escapeHtml(c)}</th>`;
  html += "</tr></thead><tbody>";
  for (const row of body) {
    html += "<tr>";
    for (const c of row) html += `<td>${escapeHtml(c)}</td>`;
    html += "</tr>";
  }
  return `${html}</tbody></table>`;
}

export function markdownToHtml(md: string): string {
  const text = md || "";
  if (text.trim().startsWith("<")) return sanitizeHtml(text);
  const lines = text.split("\n");
  const parts: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const stripped = lines[i].trim();
    if (!stripped) {
      parts.push("<p><br></p>");
      i++;
      continue;
    }
    if (isMdTableRow(stripped)) {
      const tbl: string[] = [];
      while (i < lines.length && isMdTableRow(lines[i].trim())) {
        tbl.push(lines[i]);
        i++;
      }
      parts.push(mdTableLinesToHtml(tbl));
      continue;
    }
    if (stripped.startsWith("### ")) parts.push(`<h3>${escapeHtml(stripped.slice(4))}</h3>`);
    else if (stripped.startsWith("## ")) parts.push(`<h2>${escapeHtml(stripped.slice(3))}</h2>`);
    else if (stripped.startsWith("# ")) parts.push(`<h1>${escapeHtml(stripped.slice(2))}</h1>`);
    else if (stripped.startsWith("- ")) parts.push(`<ul><li>${escapeHtml(stripped.slice(2))}</li></ul>`);
    else parts.push(`<p>${escapeHtml(stripped)}</p>`);
    i++;
  }
  return parts.join("") || "<p></p>";
}

/** Remove tables with no visible text (avoids empty grids at top of page). */
export function stripEmptyTables(html: string): string {
  if (typeof DOMParser === "undefined") return html;
  const doc = new DOMParser().parseFromString(html || "", "text/html");
  doc.querySelectorAll("table").forEach((table) => {
    const text = (table.textContent || "").replace(/\s+/g, "").trim();
    if (!text) table.remove();
  });
  return doc.body.innerHTML.trim() || "<p></p>";
}

export function sanitizeHtml(html: string): string {
  let t = html || "";
  t = t.replace(/\|[-:\s|]+\|/g, "");
  t = t.replace(/^\s*\|.+\|\s*$/gm, "");
  return stripEmptyTables(t.trim() || "<p></p>");
}

export function appendHtmlFragment(doc: string, fragment: string): string {
  const f = (fragment || "").trim();
  if (!f) return doc || "<p></p>";
  const base = (doc || "").trim();
  return base ? `${base}<p></p>${f}` : f;
}

export function normalizeContent(content: string, format?: string): { html: string; format: "html" } {
  if (format === "html" || content.trim().startsWith("<")) {
    return { html: sanitizeHtml(content), format: "html" };
  }
  return { html: markdownToHtml(content), format: "html" };
}

export type OutlineSection = { id: string; level: number; title: string };

export function parseOutlineFromHtml(html: string): OutlineSection[] {
  if (typeof DOMParser === "undefined") return [];
  const doc = new DOMParser().parseFromString(html || "<p></p>", "text/html");
  const sections: OutlineSection[] = [];
  doc.querySelectorAll("h1, h2, h3").forEach((el, idx) => {
    const tag = el.tagName.toLowerCase();
    const level = tag === "h1" ? 1 : tag === "h2" ? 2 : 3;
    const title = (el.textContent || "").trim() || `Section ${idx + 1}`;
    const id = `outline-${idx}`;
    el.id = id;
    sections.push({ id, level, title });
  });
  return sections;
}
