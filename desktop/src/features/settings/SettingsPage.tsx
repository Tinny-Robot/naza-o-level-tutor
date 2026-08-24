import { Card } from "../../components/ui/Card";
import styles from "../pages.module.css";

export function SettingsPage() {
  return (
    <div className={styles.page}>
      <h1 className={styles.heroTitle} style={{ fontSize: 32 }}>
        Settings
      </h1>
      <p className={styles.muted}>
        Preferences and privacy for your learning on this device.
      </p>

      <Card lift={false}>
        <h2 className={styles.sectionTitle}>Theme</h2>
        <p className={styles.muted} style={{ marginTop: 8 }}>
          Dark mode is locked for ADTC demo - premium slate + electric blue.
        </p>
      </Card>

      <Card lift={false}>
        <h2 className={styles.sectionTitle}>Privacy</h2>
        <p className={styles.muted} style={{ marginTop: 8 }}>
          Your learning profile and chat history stay on this device.
        </p>
      </Card>
    </div>
  );
}
