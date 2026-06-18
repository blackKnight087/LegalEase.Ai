/** Split HTML into A4 pages at page-break markers for multi-page editor preview. */
export function splitHtmlIntoPages(html: string): string[] {
  const raw = html || "<p></p>";
  const parts = raw.split(/<hr[^>]*data-page-break[^>]*\/?>/i);
  return parts.map((p) => p.trim() || "<p><br></p>");
}

export function mergePagesToHtml(pages: string[]): string {
  return pages.filter(Boolean).join('<hr data-page-break="true" />');
}
