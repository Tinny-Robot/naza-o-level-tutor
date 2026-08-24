"""Rule-based offline query router: Study (RAG) vs General (LLM-only).

Classification uses static in-repo keyword / regex heuristics only - no HTTP,
cloud APIs, Hugging Face downloads, or LLM calls for routing.
"""

from __future__ import annotations

import re
from enum import Enum

# ---------------------------------------------------------------------------
# Extensible mode enum (handlers for QUIZ / REVISION / etc. come later)
# ---------------------------------------------------------------------------


class QueryMode(Enum):
    STUDY = "study"
    GENERAL = "general"
    LESSON = "lesson"
    # future: QUIZ, REVISION, SRS, PRACTICE_EXAM


# ---------------------------------------------------------------------------
# Static detectors (module-level frozensets for reuse by future modes)
# ---------------------------------------------------------------------------

# Phrases that request a structured lesson (checked before Study/General).
LESSON_INTENT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bteach\s+me\b",
        r"\bhelp\s+me\s+(?:to\s+)?(?:learn|understand)\b",
        r"\bi\s+want\s+to\s+learn\b",
        r"\blearn(?:\s+about)?\b",
        r"\blesson\s+on\b",
        r"\bexplain\s+the\s+topic\b",
        r"\bgive\s+me\s+a\s+lesson\b",
        r"\bwalk\s+me\s+through\b",
        r"\bcan\s+you\s+teach\b",
    )
)

EXAM_BOARD_TERMS: frozenset[str] = frozenset(
    {
        "waec",
        "neco",
        "jamb",
        "o-level",
        "o level",
        "olevel",
        "ssce",
        "gce",
        "bece",
    }
)

SUBJECT_TERMS: frozenset[str] = frozenset(
    {
        "english",
        "english language",
        "mathematics",
        "maths",
        "math",
        "physics",
        "chemistry",
        "further maths",
        "further mathematics",
    }
)

EXAM_LANGUAGE: frozenset[str] = frozenset(
    {
        "past question",
        "past questions",
        "exam question",
        "exam questions",
        "syllabus",
        "scheme of work",
        "marking scheme",
        "paper 1",
        "paper 2",
        "paper 3",
        "objective questions",
        "theory questions",
        "essay question",
    }
)

# Curriculum / topic cues drawn from eval subjects and common O-Level terms.
CURRICULUM_KEYWORDS: frozenset[str] = frozenset(
    {
        # English
        "concord",
        "subject-verb",
        "subject verb",
        "lexeme",
        "lexis",
        "comprehension",
        "summary writing",
        "essay writing",
        "letter writing",
        "oral english",
        "parts of speech",
        "clause",
        "syntax",
        "pronunciation",
        "stress pattern",
        "figure of speech",
        "idiom",
        "register",
        # Mathematics
        "quadratic",
        "quadratic equation",
        "simultaneous equation",
        "logarithm",
        "logarithms",
        "mensuration",
        "trigonometry",
        "algebra",
        "geometry",
        "coordinate geometry",
        "calculus",
        "differentiation",
        "integration",
        "probability",
        "statistics",
        "set theory",
        "number base",
        "number bases",
        "indices",
        "surd",
        "surds",
        "matrix",
        "matrices",
        "progression",
        "arithmetic progression",
        "geometric progression",
        "latitude",
        "longitude",
        "bearing",
        "circle theorem",
        "circle theorems",
        # Physics
        "ohm's law",
        "ohms law",
        "ohm",
        "electromotive force",
        "emf",
        "kinematics",
        "projectile",
        "projectiles",
        "mechanics",
        "newton",
        "newton's law",
        "waves",
        "optics",
        "refraction",
        "reflection",
        "diffraction",
        "thermal physics",
        "heat capacity",
        "latent heat",
        "radioactive",
        "half-life",
        "half life",
        "magnetism",
        "electricity",
        "capacitor",
        "resistance",
        "voltage",
        "current",
        "force",
        "momentum",
        "velocity",
        "acceleration",
        "density",
        "pressure",
        "work energy power",
        # Chemistry
        "electrolysis",
        "faraday",
        "stoichiometry",
        "mole concept",
        "molar mass",
        "acid",
        "base",
        "salt",
        "titration",
        "redox",
        "oxidation",
        "reduction",
        "organic chemistry",
        "hydrocarbon",
        "alkane",
        "alkene",
        "alkyne",
        "saponification",
        "periodic table",
        "atomic structure",
        "electron configuration",
        "valence",
        "ion",
        "isotope",
        "compound",
        "element",
        "reaction",
        "chemical equation",
        "balancing equation",
        "states of matter",
        "gas law",
        "boyle",
        "charles law",
        "avogadro",
    }
)

STUDY_VERBS: frozenset[str] = frozenset(
    {
        "explain",
        "solve",
        "derive",
        "calculate",
        "define",
        "describe",
        "differentiate",
        "integrate",
        "prove",
        "simplify",
        "factorise",
        "factorize",
        "expand",
        "evaluate",
        "find",
        "compute",
        "outline",
        "state",
        "distinguish",
        "compare",
        "contrast",
    }
)

GREETING_TERMS: frozenset[str] = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "hiya",
        "howdy",
        "good morning",
        "good afternoon",
        "good evening",
        "good night",
        "greetings",
        "what's up",
        "whats up",
        "how are you",
        "how're you",
        "thanks",
        "thank you",
        "bye",
        "goodbye",
    }
)

GENERAL_TOPIC_TERMS: frozenset[str] = frozenset(
    {
        # Technology / programming
        "python",
        "javascript",
        "typescript",
        "java",
        "c++",
        "golang",
        "rust",
        "programming",
        "programmer",
        "software",
        "code",
        "coding",
        "function",
        "algorithm",
        "api",
        "database",
        "sql",
        "linux",
        "git",
        "github",
        "docker",
        "kubernetes",
        "web development",
        "app development",
        "debugging",
        "refactor",
        # AI / ML (non-curriculum framing)
        "artificial intelligence",
        "machine learning",
        "deep learning",
        "neural network",
        "transformer",
        "transformers",
        "llm",
        "chatgpt",
        "gpt",
        "nlp",
        "computer vision",
        # Careers / business / life
        "startup",
        "startups",
        "entrepreneur",
        "entrepreneurship",
        "business plan",
        "career",
        "careers",
        "resume",
        "cv writing",
        "interview tips",
        "productivity",
        "time management",
        "philosophy",
        "stoicism",
        "meditation",
        "motivation",
        "relationship advice",
        "dating",
        "investing",
        "crypto",
        "cryptocurrency",
        "bitcoin",
        "stock market",
    }
)

_WORD_RE = re.compile(r"[a-z0-9']+", re.IGNORECASE)
_WHAT_IS_RE = re.compile(
    r"^\s*(?:what\s+is|what's|whats|who\s+is|who's)\s+(.+?)\s*\??\s*$",
    re.IGNORECASE,
)


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _contains_any(text: str, terms: frozenset[str]) -> bool:
    for term in terms:
        if " " in term or "-" in term:
            if term in text:
                return True
        else:
            # Whole-word match for single tokens to avoid "hi" in "this".
            if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text):
                return True
    return False


def _has_study_verb(text: str) -> bool:
    return _contains_any(text, STUDY_VERBS)


def _has_subject_or_curriculum(text: str) -> bool:
    return _contains_any(text, SUBJECT_TERMS) or _contains_any(
        text, CURRICULUM_KEYWORDS
    )


def _is_pure_greeting(text: str) -> bool:
    """True when the utterance is only a greeting (optional punctuation)."""
    stripped = re.sub(r"[^\w\s']", " ", text)
    stripped = " ".join(stripped.split())
    if not stripped:
        return False
    if stripped in GREETING_TERMS:
        return True
    # Multi-word greetings already covered; allow "hi there" / "hello friend"
    words = stripped.split()
    if len(words) <= 3 and words[0] in {"hi", "hello", "hey", "hiya", "howdy"}:
        return True
    if stripped.startswith("good ") and any(
        stripped.startswith(g) for g in (
            "good morning",
            "good afternoon",
            "good evening",
            "good night",
        )
    ):
        return len(words) <= 4
    return False


def _what_is_target(text: str) -> str | None:
    match = _WHAT_IS_RE.match(text)
    if not match:
        return None
    return match.group(1).strip().lower()


def is_lesson_intent(text: str) -> bool:
    """True when the utterance asks for a structured teach/learn lesson."""
    normalized = _normalize(text)
    if not normalized:
        return False
    # Avoid treating "I learned that…" / past tense as a lesson request.
    if re.search(r"\bi\s+(?:just\s+)?learned\b", normalized):
        return False
    return any(p.search(normalized) for p in LESSON_INTENT_PATTERNS)


class QueryRouter:
    """Classify a user question into :class:`QueryMode` with offline heuristics."""

    def classify(self, question: str) -> QueryMode:
        cleaned = question.strip()
        if not cleaned:
            return QueryMode.GENERAL

        text = _normalize(cleaned)

        # Structured lesson requests win (before Study Q&A).
        if is_lesson_intent(text):
            return QueryMode.LESSON

        # Explicit STUDY cues win over GENERAL (including mixed greetings).
        if _contains_any(text, EXAM_BOARD_TERMS):
            return QueryMode.STUDY
        if _contains_any(text, EXAM_LANGUAGE):
            return QueryMode.STUDY
        if _contains_any(text, SUBJECT_TERMS) and (
            _has_study_verb(text)
            or _contains_any(text, CURRICULUM_KEYWORDS)
            or _contains_any(text, EXAM_LANGUAGE)
            or len(text.split()) <= 6
        ):
            return QueryMode.STUDY
        if _contains_any(text, CURRICULUM_KEYWORDS):
            return QueryMode.STUDY
        if _has_study_verb(text) and _has_subject_or_curriculum(text):
            return QueryMode.STUDY

        # Pure greetings → GENERAL.
        if _is_pure_greeting(text):
            return QueryMode.GENERAL

        # Clear general-topic cues.
        if _contains_any(text, GENERAL_TOPIC_TERMS):
            return QueryMode.GENERAL

        # Ambiguous "what is X" → GENERAL unless X matches curriculum terms.
        target = _what_is_target(text)
        if target is not None:
            if _contains_any(target, CURRICULUM_KEYWORDS) or _contains_any(
                target, SUBJECT_TERMS
            ):
                return QueryMode.STUDY
            return QueryMode.GENERAL

        # Study verb alone without curriculum context → treat as general chat.
        if _has_study_verb(text) and not _has_subject_or_curriculum(text):
            # Short school-style prompts like "solve for x" still look academic.
            if re.search(r"\b(?:for\s+x|equation|formula|theorem)\b", text):
                return QueryMode.STUDY
            return QueryMode.GENERAL

        # Default: prefer GENERAL for casual / out-of-domain chat.
        return QueryMode.GENERAL


_router: QueryRouter | None = None


def get_router() -> QueryRouter:
    """Return a shared :class:`QueryRouter` singleton."""
    global _router
    if _router is None:
        _router = QueryRouter()
    return _router


def reset_router() -> None:
    """Clear the singleton (tests only)."""
    global _router
    _router = None
