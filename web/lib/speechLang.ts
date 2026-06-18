/** Map UI language labels to Whisper ISO 639-1 codes. */
const LABEL_TO_CODE: Record<string, string> = {
  english: "en",
  hindi: "hi",
  tamil: "ta",
  marathi: "mr",
  bengali: "bn",
  gujarati: "gu",
};

export function uiLangToCode(lang: string): string {
  const raw = (lang || "English").trim();
  if (/^[a-z]{2}$/i.test(raw)) return raw.toLowerCase();
  return LABEL_TO_CODE[raw.toLowerCase()] || "en";
}

export const toWhisperLang = uiLangToCode;

export function isEnglishLang(lang: string): boolean {
  return uiLangToCode(lang) === "en";
}

export function browserSpeechLang(code: string): string {
  const c = (code || "en").toLowerCase();
  if (c === "en") {
    const nav = typeof navigator !== "undefined" ? navigator.language : "";
    if (nav.startsWith("en")) return nav;
    return "en-IN";
  }
  const map: Record<string, string> = {
    hi: "hi-IN",
    ta: "ta-IN",
    mr: "mr-IN",
    bn: "bn-IN",
    gu: "gu-IN",
  };
  return map[c] || `${c}-IN`;
}
