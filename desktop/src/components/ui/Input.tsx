import { forwardRef, type InputHTMLAttributes, type TextareaHTMLAttributes } from "react";
import styles from "./ui.module.css";

export function Input({ className = "", ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={`${styles.input} ${className}`} {...props} />;
}

export const TextArea = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement>
>(function TextArea(props, ref) {
  return <textarea ref={ref} className={styles.textarea} {...props} />;
});
