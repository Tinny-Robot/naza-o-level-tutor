import { NavLink } from "react-router-dom";
import { Naza } from "../naza/Naza";
import { useLanguage } from "../../i18n/LanguageProvider";
import { BRAND, NAV_ITEMS } from "./nav";
import styles from "./layout.module.css";

export function Sidebar() {
  const { t } = useLanguage();
  return (
    <aside className={styles.sidebar}>
      <div className={styles.brand}>
        <div className={styles.logoMark}>
          <Naza pose="idle" size={40} />
        </div>
        <div className={styles.brandText}>
          <span className={styles.brandTitle}>{BRAND.name}</span>
          <span className={styles.brandSub}>{t(BRAND.taglineKey)}</span>
        </div>
      </div>

      <nav className={styles.nav} aria-label={t("nav.main")}>
        {NAV_ITEMS.map(({ to, labelKey, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            title={t(labelKey)}
            className={({ isActive }) =>
              `${styles.navItem} ${isActive ? styles.navItemActive : ""}`
            }
          >
            <Icon size={18} strokeWidth={2} />
            <span>{t(labelKey)}</span>
          </NavLink>
        ))}
      </nav>

      <div className={styles.sidebarFoot}>
        <p className={styles.sidebarExams}>{t("sidebar.exams")}</p>
      </div>
    </aside>
  );
}
