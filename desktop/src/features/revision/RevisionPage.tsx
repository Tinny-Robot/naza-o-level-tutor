import { useCallback, useEffect, useState } from "react";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { ProgressRing } from "../../components/ui/ProgressRing";
import { ApiError, OFFLINE_ENGINE_MESSAGE } from "../../services/api";
import { getRevision } from "../../services/revision";
import {
  loadSavedRevisionCards,
  type SavedRevisionCard,
} from "../../services/revisionCards";
import type { RevisionPayload } from "../../services/types";
import styles from "../pages.module.css";

export function RevisionPage() {
  const [card, setCard] = useState<RevisionPayload | null>(null);
  const [savedCards, setSavedCards] = useState<SavedRevisionCard[]>([]);
  const [activeSaved, setActiveSaved] = useState<SavedRevisionCard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [flipped, setFlipped] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setFlipped(false);
    setActiveSaved(null);
    setSavedCards(loadSavedRevisionCards());
    try {
      setCard(await getRevision());
    } catch (err) {
      setCard(null);
      setError(err instanceof ApiError ? err.message : OFFLINE_ENGINE_MESSAGE);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    function onFocus() {
      setSavedCards(loadSavedRevisionCards());
    }
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, []);

  if (loading) {
    return (
      <div className={styles.page}>
        <p className={styles.muted}>Loading revision…</p>
      </div>
    );
  }

  if ((error || !card) && savedCards.length === 0) {
    return (
      <div className={styles.page}>
        <Card lift={false} className={styles.empty}>
          <p style={{ marginBottom: 12 }}>{error ?? OFFLINE_ENGINE_MESSAGE}</p>
          <Button onClick={() => void load()}>Retry</Button>
        </Card>
      </div>
    );
  }

  const displayFront = activeSaved?.front ?? card?.front ?? "";
  const displayBack = activeSaved?.back ?? card?.back ?? "";

  return (
    <div className={styles.page}>
      <div className={styles.rowBetween}>
        <div>
          <div className={styles.eyebrow}>Spaced repetition</div>
          <h1 className={styles.heroTitle} style={{ fontSize: 32 }}>
            Revision
          </h1>
        </div>
        {card ? <ProgressRing value={card.strength} label={`${card.strength}%`} /> : null}
      </div>

      <button
        type="button"
        className={styles.flashcard}
        style={{
          width: "100%",
          border: "1px solid var(--color-border)",
          borderRadius: "var(--radius-lg)",
          color: "inherit",
        }}
        onClick={() => setFlipped((f) => !f)}
        aria-label={flipped ? "Card back - flip to front" : "Card front - flip to back"}
      >
        {flipped ? displayBack : displayFront}
        <p className={styles.muted} style={{ marginTop: 16, fontSize: 13 }}>
          {activeSaved ? "Saved from Lesson Mode · " : ""}
          Tap to flip
        </p>
      </button>

      <div className={styles.pillRow} style={{ justifyContent: "center" }}>
        <Button variant="danger">Again</Button>
        <Button variant="ghost">Hard</Button>
        <Button variant="secondary">Good</Button>
        <Button>Easy</Button>
      </div>

      {card ? (
        <Card lift={false}>
          <h2 className={styles.sectionTitle}>Review schedule</h2>
          <p className={styles.muted} style={{ marginTop: 8 }}>
            {card.next_review}
          </p>
        </Card>
      ) : null}

      <Card lift={false}>
        <h2 className={styles.sectionTitle}>Saved from lessons</h2>
        {savedCards.length === 0 ? (
          <p className={styles.muted} style={{ marginTop: 8 }}>
            Finish a lesson and tap “Save to Revision” to collect flashcards here.
          </p>
        ) : (
          <ul className={styles.lessonList}>
            {savedCards.map((c) => {
              const selected =
                activeSaved?.front === c.front && activeSaved?.back === c.back;
              return (
                <li key={`${c.front}-${c.savedAt}`}>
                  <button
                    type="button"
                    className={`${styles.answerCard} ${selected ? styles.answerSelected : ""}`}
                    style={{ width: "100%", marginTop: 8 }}
                    onClick={() => {
                      setActiveSaved(c);
                      setFlipped(false);
                    }}
                  >
                    {c.front}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        {activeSaved ? (
          <div className={styles.pillRow} style={{ marginTop: 12 }}>
            <Button
              variant="ghost"
              onClick={() => {
                setActiveSaved(null);
                setFlipped(false);
              }}
            >
              Back to scheduled card
            </Button>
          </div>
        ) : null}
      </Card>
    </div>
  );
}
