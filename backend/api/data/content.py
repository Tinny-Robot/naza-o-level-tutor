"""Static local learning payloads for non-AI desktop screens."""

from __future__ import annotations

LESSON = {
    "subject": "Physics",
    "topic": "Optics",
    "title": "Refraction of light",
    "duration_min": 12,
    "sections": [
        {
            "heading": "1. The idea",
            "body": (
                "Refraction is the change in direction of a light ray when it crosses "
                "the boundary between two media of different optical densities - like "
                "air and glass."
            ),
        },
        {
            "heading": "2. Illustration",
            "body": "Illustration placeholder - ray diagram (incident / refracted / normal)",
            "kind": "illustration",
        },
        {
            "heading": "3. Example",
            "body": (
                "When light enters glass from air, it slows down and bends toward the "
                "normal. Leaving glass into air, it speeds up and bends away from the normal."
            ),
        },
        {
            "heading": "4. Practice",
            "body": "Which quantity stays the same across the boundary?",
            "options": ["Wavelength", "Speed", "Frequency"],
            "answer": "Frequency",
        },
    ],
    "summary": [
        "Speed and wavelength change; frequency does not.",
        "Snell’s law links angles to refractive indices.",
    ],
}

QUIZ = {
    "id": "q1",
    "subject": "Physics",
    "prompt": (
        "A ray of light travels from air into glass. Which quantity remains unchanged?"
    ),
    "options": [
        {"key": "A", "text": "Wavelength"},
        {"key": "B", "text": "Speed"},
        {"key": "C", "text": "Frequency"},
        {"key": "D", "text": "Amplitude"},
    ],
    "answer": "C",
}

SUBJECTS = [
    {
        "id": "english",
        "name": "English",
        "mastery": 78,
        "color": "#3B82F6",
        "topic": "Concord",
    },
    {
        "id": "mathematics",
        "name": "Mathematics",
        "mastery": 64,
        "color": "#7C3AED",
        "topic": "Quadratics",
    },
    {
        "id": "physics",
        "name": "Physics",
        "mastery": 71,
        "color": "#22D3EE",
        "topic": "Refraction",
    },
    {
        "id": "chemistry",
        "name": "Chemistry",
        "mastery": 58,
        "color": "#10B981",
        "topic": "Electrolysis",
    },
]

# Deterministic heatmap (35 cells) - avoid random values at request time.
HEATMAP = [
    {"day": i, "value": (i * 3 + 1) % 5}
    for i in range(35)
]

PROGRESS = {
    "streak": 7,
    "xp_week": 480,
    "accuracy": 86,
    "heatmap": HEATMAP,
    "subjects": SUBJECTS,
    "weak_topic": "Chemistry · Titration · revisit with AI Tutor or flashcards",
}

REVISION = {
    "front": "What is subject-verb concord?",
    "back": (
        "Agreement between subject and verb: singular subjects take singular verbs; "
        "plural subjects take plural verbs. Indefinite pronouns like each/everyone "
        "take singular verbs."
    ),
    "strength": 72,
    "next_review": "Next review in ~1 day · Memory strength indicator above updates "
    "as you rate cards.",
}
