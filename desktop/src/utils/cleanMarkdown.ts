import { stripChunkCitations } from "./stripChunkCitations";

/**
 * Clean LLM-generated text for display:
 * 1. Unwraps accidental JSON wrappers (e.g. `{"answer": "...", ...}`).
 * 2. Unescapes literal `\n` and `\t` into real whitespace.
 * 3. Normalizes web-scraped KaTeX/MathML artifacts (e.g. `\nV\nV` -> `$V$`).
 * 4. Strips chunk citations (`[Chunk 12]`).
 */
export function cleanMarkdown(text: string): string {
  if (!text) return "";
  let s = text;

  // 1. Unwrap JSON wrapper if the model outputted a JSON object
  s = s.replace(/^\s*\{\s*"(?:answer|explanation|text|response|reply|content)"\s*:\s*"/i, "");
  // Strip trailing JSON closing if present
  s = s.replace(/"\s*\}?\s*$/i, "");

  // 2. Unescape literal \n, \t, and escaped quotes
  s = s.replace(/\\n/g, "\n").replace(/\\t/g, "\t").replace(/\\"/g, '"');

  // 3. Fix duplicated MathML / KaTeX scraping artifacts:
  // e.g. single character on newline followed by same character: \nV\nV -> $V$
  s = s.replace(/\n([A-Za-z0-9])\n\1\b/g, (_, g) => ` $${g}$ `);
  // e.g. multiline split symbols followed by compacted formula
  s = s.replace(/(?:\n[A-Za-z0-9=∝/+\-Δ]+)+\n([A-Za-z0-9=∝/+\-Δ]+)/g, (_, g) => ` $${g}$ `);

  // Convert bare unicode math symbols to LaTeX equivalents
  s = s.replace(/∝/g, " \\propto ").replace(/Δ/g, "\\Delta ");

  return stripChunkCitations(s).trim();
}
