import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Outlet, useLocation } from "react-router-dom";
import { useLanguage } from "../../i18n/LanguageProvider";
import type { MessageKey } from "../../i18n/en";
import { useMotionVariants } from "../../motion/variants";
import { CommandBar } from "./CommandBar";
import { CommandPalette } from "./CommandPalette";
import { OnboardingModal } from "./OnboardingModal";
import { SettingsModal } from "./SettingsModal";
import { Sidebar } from "./Sidebar";
import styles from "./layout.module.css";

const PAGE_TITLES: { prefix: string; key: MessageKey }[] = [
  { prefix: "/learn", key: "nav.learn" },
  { prefix: "/tutor", key: "nav.tutor" },
  { prefix: "/practice", key: "nav.practice" },
  { prefix: "/exams", key: "nav.exams" },
  { prefix: "/progress", key: "nav.progress" },
];

function useDocumentTitle(pathname: string) {
  const { t } = useLanguage();
  useEffect(() => {
    const match = PAGE_TITLES.find(({ prefix }) => pathname.startsWith(prefix));
    document.title = match
      ? `${t(match.key)} · Naza`
      : `Naza · ${t("brand.tagline")}`;
  }, [pathname, t]);
}

export function AppShell() {
  const location = useLocation();
  useDocumentTitle(location.pathname);
  const { page } = useMotionVariants();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const searchRef = useRef<HTMLButtonElement>(null);

  const closePalette = useCallback(() => {
    setPaletteOpen(false);
    window.requestAnimationFrame(() => searchRef.current?.focus());
  }, []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((open) => !open);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className={styles.shell}>
      <Sidebar />
      <CommandBar
        searchButtonRef={searchRef}
        onOpenPalette={() => setPaletteOpen(true)}
        onOpenSettings={() => setSettingsOpen(true)}
      />
      <main className={styles.main}>
        <AnimatePresence mode="wait">
          <motion.div
            key={location.pathname}
            className={styles.pageSlot}
            variants={page}
            initial="initial"
            animate="animate"
            exit="exit"
          >
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </main>
      <CommandPalette
        open={paletteOpen}
        onClose={closePalette}
        onOpenSettings={() => {
          setPaletteOpen(false);
          setSettingsOpen(true);
        }}
      />
      <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
      <OnboardingModal />
    </div>
  );
}
