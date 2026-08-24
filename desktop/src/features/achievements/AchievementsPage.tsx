import { motion } from "framer-motion";
import { Lock, Trophy } from "lucide-react";
import { Card } from "../../components/ui/Card";
import { staggerContainer, staggerItem } from "../../motion/variants";
import { achievements } from "../../mocks/data";
import styles from "../pages.module.css";

export function AchievementsPage() {
  return (
    <motion.div
      className={styles.page}
      variants={staggerContainer}
      initial="initial"
      animate="animate"
    >
      <div>
        <h1 className={styles.heroTitle} style={{ fontSize: 32 }}>
          Achievements
        </h1>
        <p className={styles.muted}>Unlock badges as you learn - never childish, always earned.</p>
      </div>
      <div className={styles.grid3}>
        {achievements.map((a) => (
          <motion.div key={a.id} variants={staggerItem}>
            <Card>
              <div className={styles.rowBetween}>
                {a.unlocked ? (
                  <Trophy color="var(--color-warning)" size={22} />
                ) : (
                  <Lock color="var(--color-text-dim)" size={20} />
                )}
                <span className={styles.muted}>{a.unlocked ? "Unlocked" : "Locked"}</span>
              </div>
              <h3 style={{ marginTop: 12, fontSize: 18 }}>{a.title}</h3>
              <p className={styles.muted}>{a.desc}</p>
            </Card>
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}
