export type AppLanguage = "English" | "Hausa";

export type MessageVars = Record<string, string | number>;

export function interpolate(template: string, vars?: MessageVars): string {
  if (!vars) return template;
  let out = template;
  for (const [key, value] of Object.entries(vars)) {
    out = out.replaceAll(`{${key}}`, String(value));
  }
  return out;
}
