import { Component, type ErrorInfo, type ReactNode } from "react";
import styles from "./layout.module.css";

type Props = { children: ReactNode };
type State = { hasError: boolean };

function isHausa() {
  return typeof document !== "undefined" && document.documentElement.lang === "ha";
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("UI error", error, info);
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    const ha = isHausa();
    return (
      <div className={styles.crashScreen} role="alert">
        <div className={styles.modal}>
          <h2 className={styles.crashTitle}>
            {ha ? "Wani kuskure ya faru" : "Something went wrong"}
          </h2>
          <p className={styles.modalLead}>
            {ha
              ? "Sake loda wannan shafi, ko koma gida ka ci gaba daga can."
              : "Reload this page, or go home and continue from there."}
          </p>
          <div className={styles.modalActions}>
            <button
              type="button"
              className={styles.fallbackBtn}
              onClick={() => window.location.reload()}
            >
              Reload
            </button>
            <button
              type="button"
              className={styles.fallbackBtnPrimary}
              onClick={() => {
                window.location.hash = "#/";
                window.location.reload();
              }}
            >
              Go home
            </button>
          </div>
        </div>
      </div>
    );
  }
}
