import styles from "./naza.module.css";

export type NazaPose = "idle" | "look" | "fly";

const SRC: Record<NazaPose, string> = {
  idle: "/naza/naza-idle.svg",
  look: "/naza/naza-look.svg",
  fly: "/naza/naza-fly.svg",
};

type Props = {
  pose?: NazaPose;
  size?: number;
  speech?: string;
  animate?: boolean;
  onClick?: () => void;
  alt?: string;
};

export function Naza({
  pose = "idle",
  size = 72,
  speech,
  animate = false,
  onClick,
  alt = "Naza the eagle tutor",
}: Props) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag
      type={onClick ? "button" : undefined}
      className={`${styles.wrap} ${animate ? styles.bob : ""}`}
      onClick={onClick}
      aria-label={onClick ? alt : undefined}
    >
      <img
        src={SRC[pose]}
        alt={onClick ? "" : alt}
        width={size}
        height={size}
        className={styles.img}
        style={{ width: size, height: size }}
      />
      {speech ? <p className={styles.speech}>{speech}</p> : null}
    </Tag>
  );
}
