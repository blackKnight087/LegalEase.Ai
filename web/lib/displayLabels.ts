/** User-facing labels — no third-party model names in the UI. */

export const ENGINE_CHIP_NAMES: Record<string, string> = {
  kb: "KB",
  gemini: "Web",
  web: "Web",
  llm: "LLM",
  learning: "Memory",
};

export function engineChipDisplayName(key: string): string {
  return ENGINE_CHIP_NAMES[key] || key.toUpperCase();
}

export function engineChipStatusLabel(key: string, label?: string, ok?: boolean): string {
  const raw = (label || "").trim();
  if (key === "gemini" || key === "web") {
    if (!raw || /gemini|no api key/i.test(raw)) {
      return ok ? "Web Intel on" : "Web Intel off";
    }
    if (/gemini/i.test(raw)) {
      return ok ? "Web Intel on" : "Web Intel off";
    }
  }
  return raw.replace(/\bgemini[\w.-]*/gi, "web search").slice(0, 28) || "—";
}

/** Remove ## Sources blocks and Gemini grounding redirect URLs from answer body. */
export function stripInlineWebSourcesFromBody(text: string): string {
  let out = text || "";
  out = out.replace(
    /\n#{1,3}\s*Sources(?:\s*(?:&|and)\s*Citations)?\s*\n[\s\S]*?(?=\n#{1,3}\s|\n---\s*\n\*Disclaimer|$)/gi,
    "\n"
  );
  out = out.replace(
    /\[([^\]]*)\]\(\s*https?:\/\/vertexaisearch\.cloud\.google\.com\/[^)]+\)/gi,
    "$1"
  );
  out = out.replace(
    /https?:\/\/vertexaisearch\.cloud\.google\.com\/grounding-api-redirect\/[^\s)\]"']+/gi,
    ""
  );
  out = out.replace(/\n{3,}/g, "\n\n").trim();
  return out;
}

export function stripVendorNamesFromText(text: string): string {
  return stripInlineWebSourcesFromBody(
    (text || "")
      .replace(/\bwith Gemini\b/gi, "from live legal sources")
      .replace(/\bGemini grounded\b/gi, "Live web")
      .replace(/\bGemini web intelligence\b/gi, "Open Law web intelligence")
      .replace(/\bGemini\b/g, "Open Law")
      .replace(/\bgemini[\w.-]*/g, "web search")
  );
}
