import { motion } from "framer-motion";
import type { CSSProperties, ReactNode } from "react";
import { useMotionVariants } from "../../motion/variants";
import styles from "./ui.module.css";

export function Card({
  children,
  className = "",
  lift = true,
  style,
}: {
  children: ReactNode;
  className?: string;
  lift?: boolean;
  style?: CSSProperties;
}) {
  const { hover } = useMotionVariants();
  if (!lift) {
    return (
      <div className={`${styles.card} ${className}`} style={style}>
        {children}
      </div>
    );
  }
  return (
    <motion.div className={`${styles.card} ${className}`} style={style} {...hover}>
      {children}
    </motion.div>
  );
}
