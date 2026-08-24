import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useLanguage } from "../../i18n/LanguageProvider";
import styles from "./layout.module.css";

function looksLikeQuestion(q: string) {
  const text = q.trim();
  if (!text) return false;
  if (text.includes("?")) return true;
  if (text.split(/\s+/).length >= 3) return true;
  return /^(teach|explain|what|why|how|koya|bayyana|tambayi)/i.test(text);
}

export function CommandPalette({
  open,
  onClose,
  onOpenSettings,
}: {
  open: boolean;
  onClose: () => void;
  onOpenSettings: () => void;
}) {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const commands = useMemo(
    () => [
      { id: "home", label: t("nav.home"), path: "/" as string | null },
      { id: "learn", label: t("nav.learn"), path: "/learn" },
      { id: "tutor", label: t("nav.tutor"), path: "/tutor" },
      { id: "practice", label: t("nav.practice"), path: "/practice" },
      { id: "exams", label: t("nav.exams"), path: "/exams" },
      { id: "progress", label: t("nav.progress"), path: "/progress" },
      { id: "settings", label: t("top.settings"), path: null },
    ],
    [t],
  );

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setSelected(0);
    const id = window.requestAnimationFrame(() => inputRef.current?.focus());
    return () => window.cancelAnimationFrame(id);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: globalThis.KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const needle = query.trim().toLowerCase();
  const shown = needle
    ? commands.filter((c) => c.label.toLowerCase().includes(needle))
    : commands;

  useEffect(() => {
    setSelected(0);
  }, [needle]);

  if (!open) return null;

  function go(path: string | null) {
    if (path == null) {
      onOpenSettings();
      onClose();
      return;
    }
    navigate(path);
    onClose();
  }

  function askTutor(q: string) {
    navigate(`/tutor?q=${encodeURIComponent(q)}`);
    onClose();
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (looksLikeQuestion(q)) {
      askTutor(q);
      return;
    }
    const cmd = shown[selected] ?? shown[0];
    if (cmd) {
      go(cmd.path);
      return;
    }
    if (q) askTutor(q);
  }

  function onInputKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelected((i) => Math.min(i + 1, Math.max(shown.length - 1, 0)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelected((i) => Math.max(i - 1, 0));
    }
  }

  return (
    <div className={styles.modalBackdrop} role="presentation" onClick={onClose}>
      <div
        className={styles.modal}
        role="dialog"
        aria-modal="true"
        aria-label={t("palette.title")}
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.modalHead}>
          <h2>{t("palette.title")}</h2>
        </div>
        <p className={styles.modalLead}>{t("palette.lead")}</p>
        <form onSubmit={submit}>
          <label className={styles.field}>
            <span>{t("palette.ask")}</span>
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={onInputKey}
              placeholder={t("top.ask")}
              autoComplete="off"
              aria-controls="palette-commands"
              aria-activedescendant={shown[selected] ? `palette-${shown[selected].id}` : undefined}
            />
          </label>
        </form>
        {shown.length ? (
          <div className={styles.commandList} role="listbox" id="palette-commands">
            {shown.map((cmd, i) => (
              <button
                key={cmd.id}
                id={`palette-${cmd.id}`}
                type="button"
                role="option"
                aria-selected={i === selected}
                className={`${styles.commandItem} ${i === selected ? styles.commandItemActive : ""}`}
                onMouseEnter={() => setSelected(i)}
                onClick={() => go(cmd.path)}
              >
                {cmd.label}
              </button>
            ))}
          </div>
        ) : (
          <p className={styles.commandEmpty} role="status">
            {t("palette.empty")}
          </p>
        )}
      </div>
    </div>
  );
}
