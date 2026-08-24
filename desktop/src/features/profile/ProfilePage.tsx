import { Badge } from "../../components/ui/Badge";
import { Card } from "../../components/ui/Card";
import { ProgressRing } from "../../components/ui/ProgressRing";
import { student } from "../../mocks/data";
import styles from "../pages.module.css";

export function ProfilePage() {
  const pct = Math.round((student.xp / student.xpToNext) * 100);

  return (
    <div className={styles.page}>
      <div className={styles.hero}>
        <Card>
          <div
            style={{
              width: 72,
              height: 72,
              borderRadius: 20,
              background: "linear-gradient(135deg,#3B82F6,#7C3AED)",
              display: "grid",
              placeItems: "center",
              fontFamily: "var(--font-display)",
              fontWeight: 700,
              fontSize: 28,
              marginBottom: 16,
            }}
          >
            {student.name[0]}
          </div>
          <h1 style={{ fontSize: 28 }}>{student.name}</h1>
          <p className={styles.muted}>Level {student.level} learner</p>
          <div className={styles.pillRow} style={{ marginTop: 12 }}>
            <Badge tone="success">Streak {student.streak}</Badge>
          </div>
        </Card>
        <Card lift={false}>
          <div className={styles.rowBetween}>
            <div>
              <div className={styles.statLabel}>XP progress</div>
              <div className={styles.statValue}>
                {student.xp} / {student.xpToNext}
              </div>
              <p className={styles.muted} style={{ marginTop: 8 }}>
                Goal: {student.goalToday}
              </p>
            </div>
            <ProgressRing value={pct} size={88} />
          </div>
        </Card>
      </div>
    </div>
  );
}
