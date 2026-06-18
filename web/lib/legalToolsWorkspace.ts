/** Legal Tools V2 — workspace types, curated data, client persistence. */

export type WorkspaceModule =
  | "ipc-bns"
  | "crpc-bnss"
  | "limitation"
  | "court-fee"
  | "contract"
  | "citation"
  | "legislative"
  | "confused"
  | "bulk"
  | "case-assessment"
  | "odr"
  | "saved"
  | "recent";

export type MappingRecord = Record<string, unknown>;

export const STORAGE_KEYS = {
  recent: "legalease.tools.recent",
  bookmarks: "legalease.tools.bookmarks",
  notes: "legalease.tools.notes",
  pins: "legalease.tools.pins",
} as const;

export const CONFUSED_MAPPINGS: Array<{
  ipc: string;
  bns: string;
  ipcTitle: string;
  bnsTitle: string;
  note?: string;
}> = [
  { ipc: "302", bns: "103", ipcTitle: "Murder", bnsTitle: "Punishment for murder" },
  { ipc: "420", bns: "318", ipcTitle: "Cheating", bnsTitle: "Cheating" },
  { ipc: "376", bns: "63/64", ipcTitle: "Rape", bnsTitle: "Rape / sexual assault provisions" },
  { ipc: "498A", bns: "85", ipcTitle: "Cruelty by husband", bnsTitle: "Cruelty" },
  { ipc: "304B", bns: "80", ipcTitle: "Dowry death", bnsTitle: "Dowry death" },
  { ipc: "34", bns: "3(5)", ipcTitle: "Common intention", bnsTitle: "Group liability" },
  { ipc: "124A", bns: "—", ipcTitle: "Sedition", bnsTitle: "No direct equivalent", note: "Omitted / restructured in BNS" },
];

export const RELATED_SECTIONS: Record<string, string[]> = {
  "302": ["304", "304A", "307", "34", "120B", "149"],
  "420": ["406", "409", "465", "471", "34"],
  "376": ["354", "354A", "354B", "509", "375"],
  "498A": ["304B", "306", "323", "506"],
  "304B": ["498A", "304", "306"],
  "34": ["120B", "149", "109"],
};

export const KEYWORD_QUERIES: Record<string, { act: "ipc" | "bns"; section: string }> = {
  murder: { act: "ipc", section: "302" },
  cheating: { act: "ipc", section: "420" },
  "dowry death": { act: "ipc", section: "304B" },
  rape: { act: "ipc", section: "376" },
  kidnapping: { act: "ipc", section: "363" },
};

export function inferCategory(title: string): string {
  const t = title.toLowerCase();
  if (/murder|homicide|hurt|assault|rape|kidnap|dowry|suicide|miscarriage/.test(t)) {
    return "Offences affecting the human body";
  }
  if (/theft|robbery|dacoity|extortion|cheat|forgery|counterfeit|breach of trust/.test(t)) {
    return "Offences against property";
  }
  if (/defamation|public servant|contempt|riot|unlawful assembly/.test(t)) {
    return "Offences against public order";
  }
  if (/marriage|dowry|adultery/.test(t)) return "Offences relating to marriage";
  return "General / other";
}

export type ChangeBadge = "NEW" | "MODIFIED" | "UNCHANGED" | "REPEALED";

export function legislativeChangeAnalysis(rec: MappingRecord): {
  badge: ChangeBadge;
  summary: string;
  added: string[];
  removed: string[];
  modified: string[];
  penaltyChanges: string[];
  terminologyChanges: string[];
  proceduralChanges: string[];
} {
  const mt = String(rec.mapping_type || rec.mapping_status || "");
  const oldTitle = String(rec.old_title || rec.offence_title || "");
  const newTitle = String(rec.new_title || rec.short_description || "");
  const oldSec = String(rec.old_section || rec.ipc_key || "");
  const newSec = String(rec.new_section || rec.bns_key || "");
  const punishment = rec.punishment ? String(rec.punishment) : "";
  const found = Boolean(rec.found);

  if (!found) {
    return {
      badge: "REPEALED",
      summary: "No official mapping in dataset — verify manually.",
      added: [],
      removed: ["Section not mapped in official IPC↔BNS table"],
      modified: [],
      penaltyChanges: [],
      terminologyChanges: [],
      proceduralChanges: [],
    };
  }

  if (mt.includes("No corresponding") || !newSec || newSec === "—") {
    return {
      badge: "REPEALED",
      summary: "IPC provision has no corresponding BNS section in the official mapping.",
      added: [],
      removed: [oldTitle || `IPC ${oldSec}`],
      modified: [],
      penaltyChanges: [],
      terminologyChanges: [newTitle || "Decriminalised or omitted"],
      proceduralChanges: [],
    };
  }

  const badge: ChangeBadge =
    oldSec === newSec && oldTitle.toLowerCase() === newTitle.toLowerCase()
      ? "UNCHANGED"
      : mt.includes("renumbered")
        ? "MODIFIED"
        : "MODIFIED";

  const terminologyChanges: string[] = [];
  if (oldTitle && newTitle && oldTitle.toLowerCase() !== newTitle.toLowerCase()) {
    terminologyChanges.push(`Title: "${oldTitle}" → "${newTitle}"`);
  }
  if (oldSec !== newSec) {
    terminologyChanges.push(`Section renumbered: IPC ${oldSec} → BNS ${newSec}`);
  }

  const penaltyChanges: string[] = [];
  if (punishment) penaltyChanges.push(`BNS punishment (dataset): ${punishment}`);

  return {
    badge,
    summary:
      badge === "UNCHANGED"
        ? "Substantively aligned; section number unchanged in official mapping."
        : "Renumbered or retitled under BNS per official mapping dataset.",
    added: [],
    removed: [],
    modified: terminologyChanges.length ? terminologyChanges : [`Mapped to BNS ${newSec}`],
    penaltyChanges,
    terminologyChanges,
    proceduralChanges: [],
  };
}

export function loadJson<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function saveJson(key: string, value: unknown) {
  if (typeof window === "undefined") return;
  localStorage.setItem(key, JSON.stringify(value));
}

export function pushRecent(query: string, module: WorkspaceModule) {
  const list = loadJson<Array<{ q: string; module: WorkspaceModule; at: string }>>(
    STORAGE_KEYS.recent,
    []
  );
  const next = [{ q: query, module, at: new Date().toISOString() }, ...list.filter((x) => x.q !== query)].slice(
    0,
    24
  );
  saveJson(STORAGE_KEYS.recent, next);
  return next;
}

export function parseSectionQuery(raw: string): {
  act: "ipc" | "bns" | "crpc" | "bnss" | "keyword" | null;
  section: string;
  direction: "forward" | "reverse";
} | null {
  const q = raw.trim();
  if (!q) return null;
  const lower = q.toLowerCase();
  const kw = KEYWORD_QUERIES[lower];
  if (kw) return { act: kw.act, section: kw.section, direction: kw.act === "bns" ? "reverse" : "forward" };

  let m = q.match(/^(?:ipc|i\.?p\.?c\.?)\s*(\d+[a-z]?(?:\(\d+\))?)/i);
  if (m) return { act: "ipc", section: m[1].toUpperCase(), direction: "forward" };
  m = q.match(/^(\d+[a-z]?)\s*(?:ipc|i\.?p\.?c\.?)/i);
  if (m) return { act: "ipc", section: m[1].toUpperCase(), direction: "forward" };
  m = q.match(/^(?:bns)\s*(\d+(?:\(\d+\))?)/i);
  if (m) return { act: "bns", section: m[1], direction: "reverse" };
  m = q.match(/^(?:crpc)\s*(\d+)/i);
  if (m) return { act: "crpc", section: m[1], direction: "forward" };
  m = q.match(/^(?:bnss)\s*(\d+)/i);
  if (m) return { act: "bnss", section: m[1], direction: "reverse" };
  if (/^\d+[A-Z]?(?:\(\d+\))?$/.test(q.replace(/\s/g, ""))) {
    return { act: "ipc", section: q.replace(/\s/g, "").toUpperCase(), direction: "forward" };
  }
  return { act: "keyword", section: q, direction: "forward" };
}

export function exportBulkCsv(rows: MappingRecord[]) {
  const header = "IPC,IPC Title,BNS,BNS Title,Mapping Type,Status\n";
  const body = rows
    .map((r) => {
      const ipc = String(r.old_section || r.ipc_key || "");
      const bns = r.found ? String(r.new_section || r.bns_key || "") : "";
      const ot = String(r.old_title || r.offence_title || "").replace(/"/g, '""');
      const nt = String(r.new_title || r.short_description || "").replace(/"/g, '""');
      const mt = String(r.mapping_type || r.mapping_status || "");
      const st = r.found ? "Mapped" : "Not found";
      return `"${ipc}","${ot}","${bns}","${nt}","${mt}","${st}"`;
    })
    .join("\n");
  const blob = new Blob([header + body], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "ipc-bns-bulk.csv";
  a.click();
  URL.revokeObjectURL(url);
}

export const IPC_SECTION_RE =
  /\b(?:section\s+)?(\d{1,4}[a-z]?)\s*(?:of\s+)?(?:the\s+)?(?:ipc|i\.?p\.?c\.?|indian\s+penal\s+code)\b/gi;
