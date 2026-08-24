import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Loader2 } from "lucide-react";
import styles from "./ui.module.css";

type Variant = "primary" | "secondary" | "ghost" | "danger";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  children: ReactNode;
  loading?: boolean;
};

export const Button = forwardRef<HTMLButtonElement, Props>(function Button(
  {
    variant = "primary",
    className = "",
    children,
    loading = false,
    disabled,
    ...rest
  },
  ref,
) {
  const wait = Boolean(loading || disabled);
  return (
    <button
      ref={ref}
      className={`${styles.btn} ${styles[`btn_${variant}`]} ${className}`}
      type="button"
      {...rest}
      disabled={wait}
      aria-busy={loading || undefined}
    >
      {loading ? <Loader2 className={styles.spin} size={16} aria-hidden /> : null}
      {children}
    </button>
  );
});

export function ButtonLink({
  to,
  variant = "primary",
  className = "",
  children,
}: {
  to: string;
  variant?: Variant;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link to={to} className={`${styles.btn} ${styles[`btn_${variant}`]} ${className}`}>
      {children}
    </Link>
  );
}
