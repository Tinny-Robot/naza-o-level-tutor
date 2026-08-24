import { useLanguage } from "../../i18n/LanguageProvider";
import styles from "../../features/pages.module.css";

export function ExamStemNote() {
  const { language, t } = useLanguage();
  if (language !== "Hausa") return null;
  return (
    <p className={styles.examStemNote} role="note">
      {t("exam.englishStems")}
    </p>
  );
}
