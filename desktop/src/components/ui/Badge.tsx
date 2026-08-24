import type { ReactNode } from "react";
import styles from "./ui.module.css";

type Tone = "study" | "general" | "offline" | "success";

export function Badge({
  tone = "study",
  children,
}: {
  tone?: Tone;
  children: ReactNode;
}) {
  return <span className={`${styles.badge} ${styles[`badge_${tone}`]}`}>{children}</span>;
}
