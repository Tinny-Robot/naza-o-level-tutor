"""Build student context for prompts and UI summary payloads."""

from __future__ import annotations

from typing import Any

from app.student.store import StudentStore, _utc_now, get_student_store

DEFAULT_SUBJECTS = ["mathematics", "physics", "chemistry", "english"]


def build_prompt_context(store: StudentStore | None = None) -> str:
    """Build personalized prompt context containing tutor persona and journal summary.
    
    Raw session files are never injected.
    """
    st = store or get_student_store()
    profile = st.profile()
    goals = st.goals()
    mastery = st.mastery()
    misconceptions = st.misconceptions()

    parts: list[str] = [
        "### Tutor Persona & Pedagogical Guidelines",
        f"You are Naza, an encouraging and expert AI tutor for Nigerian O-Level students (preparing for {profile.exam_target}, NECO, and JAMB).",
        "Adopt a warm, patient, and motivating tone. Anchor concepts with clear examples, and guide students step-by-step.",
    ]

    journal_parts: list[str] = []
    if goals.today:
        journal_parts.append(f"- Student today's goal: {goals.today}")

    # Weak topics (< 0.6 score)
    weak = [t for t in mastery.topics if t.score < 0.6 and t.attempts > 0]
    if weak:
        weak_strs = [f"{t.subject.title()}: {t.topic} (mastery {int(t.score * 100)}%)" for t in weak[:3]]
        journal_parts.append(f"- Areas where student struggles or needs reinforcement: {', '.join(weak_strs)}")

    # Strong topics (>= 0.7 score)
    strong = [t for t in mastery.topics if t.score >= 0.7]
    if strong:
        strong_strs = [f"{t.subject.title()}: {t.topic}" for t in strong[:3]]
        journal_parts.append(f"- Getting stronger in: {', '.join(strong_strs)}")

    # Misconceptions
    if misconceptions.items:
        misc_strs = [f"{m.subject.title()} - {m.topic}: {m.confused}" for m in misconceptions.items[-3:]]
        journal_parts.append(f"- Known misconceptions to address gently: {'; '.join(misc_strs)}")

    if journal_parts:
        parts.append("\n### Learning Journal & Student Profile")
        parts.extend(journal_parts)

    return "\n".join(parts)


def build_summary(store: StudentStore | None = None) -> dict[str, Any]:
    """Build full student summary for the desktop UI and API."""
    st = store or get_student_store()
    profile = st.profile()
    prefs = st.preferences()
    goals = st.goals()
    mastery = st.mastery()
    sessions = st.list_sessions(limit=100)

    practice_sessions = [s for s in sessions if s.get("kind") in ("practice", "quiz")]
    exam_sessions = [s for s in sessions if s.get("kind") == "exam"]
    lesson_sessions = [s for s in sessions if s.get("kind") == "lesson"]

    practice_answered = len(practice_sessions)
    correct_count = sum(1 for s in practice_sessions if s.get("correct") is True)
    accuracy = (correct_count / practice_answered) if practice_answered > 0 else None

    # Calculate weak topics
    weak_topics: list[dict[str, Any]] = []
    for t in mastery.topics:
        if t.score < 0.6 or (t.attempts > 0 and t.score < 0.7):
            weak_topics.append({
                "subject": t.subject,
                "topic": t.topic,
                "score": t.score,
            })
    weak_topics.sort(key=lambda x: x["score"])

    # Calculate subject breakdown
    subjects_map: dict[str, list[float]] = {s: [] for s in DEFAULT_SUBJECTS}
    for t in mastery.topics:
        subj = t.subject.lower()
        if subj in subjects_map:
            subjects_map[subj].append(t.score)
        else:
            subjects_map[subj] = [t.score]

    subjects_summary = []
    for s in DEFAULT_SUBJECTS:
        scores = subjects_map.get(s, [])
        m = (sum(scores) / len(scores)) if scores else 0.5
        subjects_summary.append({
            "subject": s,
            "mastery": round(m, 2),
            "topics": len(scores),
        })

    # Recommendation
    recommend_subj = "mathematics"
    recommend_top = "Quadratic Equations"
    if weak_topics:
        recommend_subj = weak_topics[0]["subject"]
        recommend_top = weak_topics[0]["topic"]

    recommendation = f"Review {recommend_top} in {recommend_subj.title()} to strengthen your foundation."

    # Build learning plan items
    plan_items = []
    if weak_topics:
        for wt in weak_topics[:3]:
            plan_items.append({
                "kind": "practice",
                "label": f"Practice: {wt['topic']}",
                "subject": wt["subject"],
                "topic": wt["topic"],
            })
    else:
        plan_items = [
            {"kind": "lesson", "label": "Lesson: Quadratic Equations", "subject": "mathematics", "topic": "Quadratic Equations"},
            {"kind": "practice", "label": "Practice: Force and Motion", "subject": "physics", "topic": "Force and Motion"},
            {"kind": "revision", "label": "Revision: Chemical Bonding", "subject": "chemistry", "topic": "Chemical Bonding"},
        ]

    # Recent activity
    recent_activity = []
    for s in sessions[:5]:
        label = s.get("label") or f"{s.get('kind', 'Activity').title()} - {s.get('topic', '')}"
        recent_activity.append({
            "kind": s.get("kind", "activity"),
            "at": s.get("recorded_at", _utc_now()),
            "label": label,
        })

    focus_areas = [wt["topic"] for wt in weak_topics[:4]] if weak_topics else ["Algebra", "Mechanics", "Atomic Structure"]

    return {
        "display_name": profile.display_name,
        "streak_days": 1,
        "goal_today": goals.today,
        "goal_weekly": goals.weekly,
        "target_exam": profile.exam_target,
        "lessons_completed": len(lesson_sessions),
        "practice_answered": practice_answered,
        "practice_accuracy": accuracy,
        "exams_taken": len(exam_sessions),
        "learning_plan": {
            "title": "Today's Study Plan",
            "items": plan_items,
            "updated_at": _utc_now(),
        },
        "weak_topics": weak_topics,
        "subjects": subjects_summary,
        "recommendation": recommendation,
        "recommend_topic": recommend_top,
        "recommend_subject": recommend_subj,
        "continue_learning": {
            "subject": recommend_subj,
            "topic": recommend_top,
            "label": f"Continue {recommend_top}",
            "course_id": None,
        },
        "recent_activity": recent_activity,
        "preferences": {
            "language": prefs.language,
            "explanation_style": prefs.explanation_style,
            "show_citations": prefs.show_citations,
            "onboarded": prefs.onboarded,
        },
        "focus_areas": focus_areas,
    }

