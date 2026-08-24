import styles from "./ui.module.css";

export function Skeleton({
  width = "100%",
  height = 16,
  className = "",
}: {
  width?: number | string;
  height?: number | string;
  className?: string;
}) {
  return (
    <div
      className={`${styles.skeleton} ${className}`}
      style={{ width, height }}
      aria-hidden
    />
  );
}
