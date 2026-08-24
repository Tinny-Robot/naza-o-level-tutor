import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { fetchStudentSummary, patchPreferences } from "../services/student";
import { en, type MessageKey } from "./en";
import { ha } from "./ha";
import { interpolate, type AppLanguage, type MessageVars } from "./types";

const DICTS: Record<AppLanguage, Record<MessageKey, string>> = {
  English: en,
  Hausa: ha,
};

function normalizeLanguage(value: string | undefined | null): AppLanguage {
  const raw = (value || "").trim().toLowerCase();
  if (raw === "hausa" || raw === "ha") return "Hausa";
  return "English";
}

type LanguageContextValue = {
  language: AppLanguage;
  t: (key: MessageKey, vars?: MessageVars) => string;
  setLanguage: (language: AppLanguage) => Promise<void>;
  refresh: () => Promise<void>;
};

const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<AppLanguage>("English");

  const apply = useCallback((next: AppLanguage) => {
    setLanguageState(next);
    document.documentElement.lang = next === "Hausa" ? "ha" : "en";
  }, []);

  const refresh = useCallback(async () => {
    try {
      const summary = await fetchStudentSummary();
      apply(normalizeLanguage(summary.preferences?.language));
    } catch {
      apply("English");
    }
  }, [apply]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const t = useCallback(
    (key: MessageKey, vars?: MessageVars) => {
      const table = DICTS[language] || en;
      return interpolate(table[key] ?? en[key] ?? key, vars);
    },
    [language],
  );

  const setLanguage = useCallback(
    async (next: AppLanguage) => {
      const lang = normalizeLanguage(next);
      await patchPreferences({ language: lang });
      apply(lang);
    },
    [apply],
  );

  const value = useMemo(
    () => ({ language, t, setLanguage, refresh }),
    [language, t, setLanguage, refresh],
  );

  return (
    <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
  );
}

export function useLanguage() {
  const ctx = useContext(LanguageContext);
  if (!ctx) {
    throw new Error("useLanguage must be used within LanguageProvider");
  }
  return ctx;
}
