"""Unified exam/practice question bank from past papers, qa.json, and pq-pdf chunks.

Deduplicates stems, keeps MCQ-only items, and attaches figures from qa.json
only when that question was given an image path that still exists on disk.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app.config import CHUNKS_PATH, DATA_DIR, EVAL_DIR, PROJECT_ROOT, RAW_DIR, QA_PATH
from app.utils.logging import get_logger

logger = get_logger(__name__)

SUBJECTS = ("english", "mathematics", "physics", "chemistry")
EXAM_BOARDS = ("WAEC", "NECO", "JAMB")

_OPTION_LINE_RE = re.compile(
    r"(?:^|[\n;])\s*([A-D])[\).\:]\s*(.+?)(?=(?:[\n;]\s*[A-D][\).\:])|$)",
    re.IGNORECASE | re.DOTALL,
)
_OPTIONS_BLOCK_RE = re.compile(
    r"Options:\s*(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_INLINE_OPTS_RE = re.compile(
    r"\bA[\).]\s*(.+?)\s+B[\).]\s*(.+?)\s+C[\).]\s*(.+?)\s+D[\).]\s*(.+?)(?:\s*$)",
    re.IGNORECASE | re.DOTALL,
)
_CHUNK_MCQ_RE = re.compile(
    r"(?:^|\s)(\d+)[\).\-]\s+"
    r"(.+?)\s+"
    r"A[\).]\s*(.+?)\s+"
    r"B[\).]\s*(.+?)\s+"
    r"C[\).]\s*(.+?)\s+"
    r"D[\).]\s*(.+?)"
    r"(?=(?:\s+\d+[\).\-])|$)",
    re.IGNORECASE | re.DOTALL,
)
# Past-paper chunk lines: Question: ... Options: A. .. B. .. Answer: B Explanation: ...
_EMBEDDED_PQ_RE = re.compile(
    r"(?:Year:\s*(?P<year>\d{4})\s*\|\s*)?"
    r"(?:Exam Board:\s*(?P<board>WAEC|NECO|JAMB)\s*\|\s*)?"
    r"(?:Paper Type:\s*(?P<paper>[^|]+)\|\s*)?"
    r"(?:Topic:\s*(?P<topic>[^\n]+?)\s+)?"
    r"Question:\s*(?P<question>.+?)\s+"
    r"Options:\s*(?P<options>.+?)\s+"
    r"Answer:\s*(?P<answer>[A-D])\b"
    r"(?:\s+Explanation:\s*(?P<explanation>.+?))?"
    r"(?=(?:\s*Year:)|$)",
    re.IGNORECASE | re.DOTALL,
)
_ANSWER_LETTER_RE = re.compile(r"^([A-D])\b", re.IGNORECASE)
_USELESS_TOPIC = re.compile(
    r"essay|composition|summary\b|theory\b|practical\b|letter format",
    re.IGNORECASE,
)


def _norm_stem(text: str) -> str:
    t = text.lower()
    t = re.sub(r"options:\s*.*$", "", t, flags=re.I | re.S)
    t = re.sub(r"\b[a-d][\).].*$", "", t, flags=re.I | re.S)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()[:160]


def _qid(*parts: str) -> str:
    raw = "|".join(parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _normalize_answer(answer: Any) -> str:
    text = str(answer or "").strip()
    m = _ANSWER_LETTER_RE.match(text)
    if m:
        return m.group(1).upper()
    if len(text) == 1 and text.upper() in {"A", "B", "C", "D"}:
        return text.upper()
    # "B - Gas Y is four..."
    m2 = re.match(r"^([A-D])\s*[-\-:]", text, re.I)
    if m2:
        return m2.group(1).upper()
    return text


def _is_letter_answer(answer: Any) -> bool:
    """True only for A/B/C/D (empty string is NOT a valid letter answer)."""
    return str(answer or "").strip().upper() in {"A", "B", "C", "D"}


# Footer / page / next-question bleed from scraped JAMB topical PDFs in qa.json
_EXAM_FOOTER_RE = re.compile(
    r"\s*(?:Page\s+\d+\s+)?(?:WAEC|NECO|JAMB)\s+"
    r"(?:Physics|Chemistry|Mathematics|English|Biology)?\s*"
    r"(?:Topical\s+)?Past Questions(?:\s+\d{4})?.*$",
    re.IGNORECASE,
)
_PAGE_FOOTER_RE = re.compile(
    r"\s*Page\s+\d+(?:\s+(?:WAEC|NECO|JAMB).*)?$",
    re.IGNORECASE,
)
_NEXT_Q_BLEED_RE = re.compile(
    r"\s+\d{1,3}\s*[--.]\s+[A-Z].*$",
)
_TABLE_BLEED_RE = re.compile(
    r"\s+COMPOUND\b.*$",
    re.IGNORECASE,
)


def _scrub_exam_noise(text: str) -> str:
    """Strip PDF page footers and next-question bleed glued onto stems/options."""
    t = str(text or "")
    t = _EXAM_FOOTER_RE.sub("", t)
    t = _PAGE_FOOTER_RE.sub("", t)
    t = _TABLE_BLEED_RE.sub("", t)
    t = _NEXT_Q_BLEED_RE.sub("", t)
    return re.sub(r"\s+", " ", t).strip(" ;.|")


def _clean_opt(text: str) -> str:
    return _scrub_exam_noise(text).strip(" ;.")


def _parse_options_from_question(question: str) -> tuple[str, list[str]] | None:
    """Return (stem, ['A. ...', ...]) or None."""
    q = question.strip()
    block = _OPTIONS_BLOCK_RE.search(q)
    if block:
        stem = q[: block.start()].strip()
        body = block.group(1)
        # Prefer semicolon-separated Options: A. ..; B. ..
        parts = re.findall(
            r"([A-D])[\).\:]\s*([^;]+)",
            body,
            flags=re.I,
        )
        if len(parts) >= 4:
            opts = [f"{p[0].upper()}. {_clean_opt(p[1])}" for p in parts[:4]]
            if len(stem) >= 20:
                return stem, opts
    # newline / inline A) B) C) D)
    inline = _INLINE_OPTS_RE.search(q.replace("\n", " "))
    if inline:
        # stem is before A.
        stem_m = re.search(r"^(.*?)\s+A[\).]\s*", q.replace("\n", " "), re.I)
        stem = _clean_opt(stem_m.group(1)) if stem_m else q[:80]
        opts = [
            f"A. {_clean_opt(inline.group(1))}",
            f"B. {_clean_opt(inline.group(2))}",
            f"C. {_clean_opt(inline.group(3))}",
            f"D. {_clean_opt(inline.group(4))}",
        ]
        if len(stem) >= 20:
            return stem, opts
    lines = _OPTION_LINE_RE.findall(q)
    if len(lines) >= 4:
        # stem = text before first option letter
        first = re.search(r"(?:^|\n)\s*[A-D][\).\:]", q, re.I)
        stem = q[: first.start()].strip() if first else q
        opts = [f"{L.upper()}. {_clean_opt(t)}" for L, t in lines[:4]]
        if len(stem) >= 20:
            return stem, opts
    return None


def _media_url(path: str) -> str:
    return f"/media?path={quote(path)}"


def _resolve_image_paths(images: list[Any]) -> list[dict[str, str]]:
    """Keep only real files. qa.json is the curated assignment list."""
    refs: list[dict[str, str]] = []
    seen: set[str] = set()
    for img in images:
        p = str(img).strip()
        if not p:
            continue
        path = Path(p)
        if not path.is_absolute():
            path = (PROJECT_ROOT / path).resolve()
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            continue
        if "_ms_" in path.name.lower():
            continue
        rel = str(path)
        if rel in seen:
            continue
        seen.add(rel)
        refs.append(
            {
                "path": rel,
                "url": _media_url(rel),
                "caption": "Refer to the diagram below.",
            }
        )
    return refs


def _path_for(subject: str) -> Path:
    return RAW_DIR / subject.lower() / "past_questions_20years.json"


@lru_cache(maxsize=1)
def _load_qa() -> tuple[dict[str, Any], ...]:
    if not QA_PATH.is_file():
        return tuple()
    data = json.loads(QA_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return tuple()
    return tuple(x for x in data if isinstance(x, dict))


@lru_cache(maxsize=1)
def _load_chunks() -> tuple[dict[str, Any], ...]:
    if not CHUNKS_PATH.is_file():
        return tuple()
    data = json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return tuple()
    return tuple(x for x in data if isinstance(x, dict))


@lru_cache(maxsize=8)
def load_subject(subject: str) -> tuple[dict[str, Any], ...]:
    path = _path_for(subject)
    if not path.is_file():
        return tuple()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return tuple()
    return tuple(x for x in data if isinstance(x, dict))


def list_topics(subject: str) -> list[str]:
    topics = {
        str(q.get("topic") or "").strip()
        for q in _unified_bank(subject)
        if str(q.get("topic") or "").strip()
    }
    return sorted(topics)


def _infer_board(source: str, exam_hint: str | None = None) -> str:
    s = (source or "").upper()
    if exam_hint:
        return exam_hint.upper()
    if "JAMB" in s:
        return "JAMB"
    if "NECO" in s:
        return "NECO"
    if "WAEC" in s:
        return "WAEC"
    return "WAEC"


def _is_useful_mcq(stem: str, options: list[str], answer: str, topic: str) -> bool:
    if len(stem) < 20 or len(options) < 4:
        return False
    if not _is_letter_answer(_normalize_answer(answer)):
        return False
    if _USELESS_TOPIC.search(topic or "") and "comprehension" not in (topic or "").lower():
        # Allow comprehension; drop pure essay/summary topics without MCQ value
        if "comprehension" not in stem.lower():
            return False
    # Drop garbage stems
    if stem.lower().startswith("page "):
        return False
    return True


def _from_past_json(subject: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for q in load_subject(subject):
        opts = q.get("options") or []
        paper = str(q.get("paper_type") or "")
        stem = str(q.get("question") or "").strip()
        answer = _normalize_answer(q.get("answer"))
        topic = str(q.get("topic") or paper or "General")
        passage = None
        if paper.lower() == "comprehension" and "Read the following passage" in stem:
            # Keep passage as context; without A-D options skip for CBT
            if not opts:
                continue
            passage = stem
        if not opts:
            parsed = _parse_options_from_question(stem)
            if not parsed:
                continue
            stem, opts = parsed
        if not _is_useful_mcq(stem, opts, answer, topic):
            continue
        # Normalize options to A. form
        norm_opts = []
        for i, opt in enumerate(opts[:4]):
            letter = "ABCD"[i]
            text = str(opt).strip()
            if re.match(r"^[A-D][\).\:]", text, re.I):
                norm_opts.append(f"{letter}. {_clean_opt(text[2:])}")
            else:
                norm_opts.append(f"{letter}. {_clean_opt(text)}")
        out.append(
            {
                "id": _qid("past", subject, stem),
                "subject": subject,
                "exam_board": str(q.get("exam_board") or "WAEC"),
                "year": q.get("year"),
                "topic": topic,
                "paper_type": paper or "Objective",
                "question": stem,
                "passage": passage,
                "options": norm_opts,
                "answer": answer,
                "explanation": str(q.get("explanation") or ""),
                "images": [],
                "source": f"past_questions_20years:{subject}",
            }
        )
    return out


def _from_qa_json(subject: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for q in _load_qa():
        if str(q.get("subject") or "").lower() != subject:
            continue
        # Skip items flagged for review (NCERT / vague / off-syllabus repairs)
        if q.get("needs_review") is True:
            continue
        topic = str(q.get("topic") or "General")
        # Prefer exam-relevant English topics; skip NCERT class readers for CBT
        if subject == "english":
            tl = topic.lower()
            if any(
                x in tl
                for x in (
                    "class10",
                    "class11",
                    "class12",
                    "first flight",
                    "hornbill",
                    "footprints",
                    "workbook",
                    "ncert",
                    "flamingo",
                    "vistas",
                    "snapshots",
                )
            ):
                continue
        raw_q = str(q.get("question") or "")
        answer = _normalize_answer(q.get("answer"))
        parsed = _parse_options_from_question(raw_q)
        if not parsed:
            continue
        stem, opts = parsed
        if not _is_useful_mcq(stem, opts, answer, topic):
            continue
        board = _infer_board(str(q.get("id") or "") + " " + topic + " " + raw_q)
        if "jamb" in (q.get("id") or "").lower() or "jamb" in topic.lower():
            board = "JAMB"
        images = _resolve_image_paths(list(q.get("images") or []))
        out.append(
            {
                "id": _qid("qa", str(q.get("id") or stem)),
                "subject": subject,
                "exam_board": board,
                "year": None,
                "topic": topic,
                "paper_type": "Objective",
                "question": stem,
                "passage": None,
                "options": opts,
                "answer": answer,
                "explanation": _scrub_exam_noise(str(q.get("explanation") or "")),
                "images": images,
                "source": f"qa.json:{q.get('id')}",
            }
        )
    return out


def _qa_answer_index(subject: str) -> dict[str, dict[str, Any]]:
    """Map normalized stems → letter answer / images from all usable qa rows."""
    index: dict[str, dict[str, Any]] = {}
    for q in _load_qa():
        if str(q.get("subject") or "").lower() != subject:
            continue
        if q.get("needs_review") is True:
            continue
        answer = _normalize_answer(q.get("answer"))
        if not _is_letter_answer(answer):
            continue
        raw_q = str(q.get("question") or "")
        parsed = _parse_options_from_question(raw_q)
        stem = parsed[0] if parsed else raw_q
        key = _norm_stem(stem)
        if not key:
            continue
        index[key] = {
            "answer": answer,
            "explanation": _scrub_exam_noise(str(q.get("explanation") or "")),
            "images": _resolve_image_paths(list(q.get("images") or [])),
            "id": q.get("id"),
        }
    return index


def _attach_answers_from_qa(items: list[dict[str, Any]], subject: str) -> list[dict[str, Any]]:
    """Fill missing answers by matching stems to qa.json letter answers."""
    qa_by_stem = _qa_answer_index(subject)
    # Also include fully-parsed MCQ stems
    for q in _from_qa_json(subject):
        qa_by_stem.setdefault(
            _norm_stem(q["question"]),
            {
                "answer": q["answer"],
                "explanation": q.get("explanation") or "",
                "images": q.get("images") or [],
                "id": q.get("id"),
            },
        )
    filled: list[dict[str, Any]] = []
    for item in items:
        if _is_letter_answer(item.get("answer")):
            # Merge qa images when chunk item has none
            if not item.get("images"):
                hit = qa_by_stem.get(_norm_stem(item["question"]))
                if hit and hit.get("images"):
                    item = {**item, "images": hit["images"]}
            filled.append(item)
            continue
        key = _norm_stem(item["question"])
        hit = qa_by_stem.get(key)
        if hit and _is_letter_answer(hit.get("answer")):
            item = {
                **item,
                "answer": hit["answer"],
                "explanation": hit.get("explanation") or item.get("explanation") or "",
                "images": item.get("images") or hit.get("images") or [],
            }
            filled.append(item)
        # else drop unanswered chunk items
    return filled


def _attach_qa_images(items: list[dict[str, Any]], subject: str) -> None:
    """Copy curated qa.json figures onto matching bank stems."""
    index = _qa_answer_index(subject)
    for item in items:
        if item.get("images"):
            continue
        hit = index.get(_norm_stem(item["question"]))
        if hit and hit.get("images"):
            item["images"] = hit["images"]


def _options_from_embedded(body: str) -> list[str] | None:
    """Parse A./B./C./D. options; require delimiter after letter so words like 'are' do not match."""
    text = (body or "").strip()
    # Space/semicolon-separated: A. foo B. bar ...
    parts = re.findall(
        r"(?:^|[\s;])([A-D])[\).\:]\s*(.+?)(?=(?:[\s;]+[A-D][\).\:])|$)",
        text,
        flags=re.I | re.DOTALL,
    )
    if len(parts) < 4:
        parts = re.findall(r"([A-D])[\).\:]\s*([^;]+)", text, flags=re.I)
    if len(parts) < 4:
        return None
    return [f"{p[0].upper()}. {_clean_opt(p[1])}" for p in parts[:4]]


def _from_chunks(subject: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in _load_chunks():
        meta = c.get("metadata") or {}
        if str(meta.get("subject") or "").lower() != subject:
            continue
        raw_text = str(c.get("text") or "")
        text = " ".join(raw_text.split())
        source = str(meta.get("source") or "")
        board = _infer_board(source)
        topic = str(meta.get("topic") or "Past Questions")
        if "_ms_" in source.lower() or source.lower().endswith("_ms.pdf"):
            continue  # marking schemes

        # 1) Embedded past-question records (English Lexis/Oral etc.)
        for m in _EMBEDDED_PQ_RE.finditer(text):
            stem = _clean_opt(m.group("question") or "")
            opts = _options_from_embedded(m.group("options") or "")
            answer = _normalize_answer(m.group("answer"))
            if not opts or not _is_useful_mcq(stem, opts, answer, m.group("topic") or topic):
                continue
            out.append(
                {
                    "id": _qid("emb", subject, stem),
                    "subject": subject,
                    "exam_board": (m.group("board") or board or "WAEC").upper(),
                    "year": m.group("year"),
                    "topic": _clean_opt(m.group("topic") or topic),
                    "paper_type": _clean_opt(m.group("paper") or "Objective"),
                    "question": stem,
                    "passage": None,
                    "options": opts,
                    "answer": answer,
                    "explanation": _clean_opt(m.group("explanation") or ""),
                    "images": [],
                    "source": source,
                }
            )

        # 2) Numbered A-D blocks (JAMB topical PDFs)
        for m in _CHUNK_MCQ_RE.finditer(text):
            stem = _clean_opt(m.group(2))
            opts = [
                f"A. {_clean_opt(m.group(3))}",
                f"B. {_clean_opt(m.group(4))}",
                f"C. {_clean_opt(m.group(5))}",
                f"D. {_clean_opt(m.group(6))}",
            ]
            if not _is_useful_mcq(stem, opts, "A", topic):
                continue
            out.append(
                {
                    "id": _qid("chunk", subject, stem),
                    "subject": subject,
                    "exam_board": board,
                    "year": None,
                    "topic": topic,
                    "paper_type": "Objective",
                    "question": stem,
                    "passage": None,
                    "options": opts,
                    "answer": "",  # fill from qa match when possible
                    "explanation": "",
                    "images": [],
                    "source": source,
                }
            )
    return out


def _sanitize_item(item: dict[str, Any]) -> dict[str, Any] | None:
    """Final scrub of stem/options; drop items that still look corrupted."""
    stem = _scrub_exam_noise(str(item.get("question") or ""))
    opts_in = list(item.get("options") or [])
    opts: list[str] = []
    for i, opt in enumerate(opts_in[:4]):
        letter = "ABCD"[i]
        text = str(opt)
        if re.match(r"^[A-D][\).\:]", text, re.I):
            body = _clean_opt(text[2:])
        else:
            body = _clean_opt(text)
        if len(body) < 1:
            return None
        # Reject options that still look like page footers or multi-question bleed
        if re.search(r"\bPast Questions\b|\bPage\s+\d+\b", body, re.I):
            return None
        if len(body) > 180:
            return None
        opts.append(f"{letter}. {body}")
    if len(opts) < 4 or len(stem) < 20:
        return None
    cleaned = dict(item)
    cleaned["question"] = stem
    cleaned["options"] = opts
    if cleaned.get("explanation"):
        cleaned["explanation"] = _scrub_exam_noise(str(cleaned["explanation"]))
    if cleaned.get("passage"):
        cleaned["passage"] = _scrub_exam_noise(str(cleaned["passage"]))
    return cleaned


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        cleaned = _sanitize_item(item)
        if not cleaned:
            continue
        key = _norm_stem(cleaned["question"])
        if not key or key in seen:
            continue
        if not _is_letter_answer(cleaned.get("answer")):
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def _extract_passage_body(question: str) -> str | None:
    q = str(question or "").strip()
    m = re.search(
        r"(?:Read the (?:following )?passage[^\n:]*:\s*)(.+)",
        q,
        flags=re.I | re.S,
    )
    if m:
        body = re.sub(r"\s+", " ", m.group(1)).strip()
        return body if len(body) >= 120 else None
    if q.lower().startswith("read the") and len(q) >= 120:
        return re.sub(r"\s+", " ", q).strip()
    return None


def _comprehension_passages(subject: str) -> list[dict[str, Any]]:
    """Build multi-item comprehension sets from past papers + qa.json passages."""
    if subject != "english":
        return []

    # Collect unique long passages
    passages: dict[str, dict[str, Any]] = {}
    for q in load_subject(subject):
        if "comprehension" not in str(q.get("paper_type") or "").lower():
            continue
        body = _extract_passage_body(str(q.get("question") or ""))
        if not body:
            # Some past items store the full prompt as the question
            raw = re.sub(r"\s+", " ", str(q.get("question") or "")).strip()
            if len(raw) >= 200:
                body = raw
        if not body:
            continue
        key = _norm_stem(body)[:80]
        passages.setdefault(
            key,
            {
                "text": body,
                "exam_board": str(q.get("exam_board") or "WAEC"),
                "year": q.get("year"),
                "source": "past_questions_comprehension",
            },
        )
    for q in _load_qa():
        if str(q.get("subject") or "").lower() != "english":
            continue
        if q.get("needs_review") is True:
            continue
        if "comprehension" not in str(q.get("topic") or "").lower():
            continue
        body = _extract_passage_body(str(q.get("question") or ""))
        if not body:
            continue
        key = _norm_stem(body)[:80]
        passages.setdefault(
            key,
            {
                "text": body,
                "exam_board": "WAEC",
                "year": None,
                "source": f"qa.json:{q.get('id')}",
            },
        )

    out: list[dict[str, Any]] = []
    for meta in passages.values():
        text = meta["text"]
        low = text.lower()
        board = meta["exam_board"]
        year = meta["year"]
        source = meta["source"]

        # Passage-specific item banks (grounded in known keys / content)
        items: list[dict[str, Any]] = []
        if "national youth orchestra" in low or "ade woke up" in low:
            items = [
                {
                    "question": "Why was Ade's heart heavy that morning?",
                    "options": [
                        "A. It was the day of his final orchestra audition.",
                        "B. He had lost his cello the night before.",
                        "C. He was travelling abroad permanently.",
                        "D. He had failed a chemistry examination.",
                    ],
                    "answer": "A",
                    "explanation": "The passage states it was the final audition for the National Youth Orchestra.",
                },
                {
                    "question": "Which detail shows Ade had prepared for a long time?",
                    "options": [
                        "A. He arrived late to the hall.",
                        "B. He had practiced for months until his fingers were raw.",
                        "C. He borrowed a cello from a friend that morning.",
                        "D. He refused to enter the grand hall.",
                    ],
                    "answer": "B",
                    "explanation": "The passage says he practiced for months until his fingers were raw.",
                },
                {
                    "question": "What grammatical name is given to 'When Ade woke up that morning'?",
                    "options": [
                        "A. Noun clause",
                        "B. Adjectival clause",
                        "C. Adverbial clause of time",
                        "D. Main clause",
                    ],
                    "answer": "C",
                    "explanation": "It is an adverbial clause of time modifying 'was heavy'.",
                },
                {
                    "question": "In the passage, the hall that 'seemed to stand in judgment' most nearly illustrates _____.",
                    "options": [
                        "A. alliteration",
                        "B. synecdoche / personification of the setting",
                        "C. onomatopoeia",
                        "D. rhyme",
                    ],
                    "answer": "B",
                    "explanation": "The hall is treated as judging him - figurative transfer of human quality / standing for the examiners.",
                },
                {
                    "question": "Which statement best captures the main idea of the passage?",
                    "options": [
                        "A. Ade faces intense pressure before an important audition.",
                        "B. Ade prefers farming to music.",
                        "C. Ade invents a new musical instrument.",
                        "D. Ade argues about school fees with his parents.",
                    ],
                    "answer": "A",
                    "explanation": "The narrative centres on Ade's anxiety and preparation for a decisive audition.",
                },
            ]
        elif "modern agriculture" in low or "chemical fertilizers" in low:
            items = [
                {
                    "question": "According to the passage, chemical fertilizers mainly harm the environment by _____.",
                    "options": [
                        "A. improving soil colour",
                        "B. contaminating water bodies and harming aquatic life",
                        "C. reducing rainfall permanently",
                        "D. increasing the price of school books",
                    ],
                    "answer": "B",
                    "explanation": "The passage links fertilizer use to water contamination and death of aquatic life.",
                },
                {
                    "question": "Clearing forests for farmland threatens wildlife mainly because it _____.",
                    "options": [
                        "A. creates more rivers",
                        "B. destroys habitats",
                        "C. cools the climate",
                        "D. increases fish population",
                    ],
                    "answer": "B",
                    "explanation": "Habitat destruction from forest clearing is stated as a major issue.",
                },
                {
                    "question": "The writer's primary concern in the passage is _____.",
                    "options": [
                        "A. celebrating modern farming without criticism",
                        "B. environmental problems linked to modern agriculture",
                        "C. teaching how to play the cello",
                        "D. explaining computer programming",
                    ],
                    "answer": "B",
                    "explanation": "The passage balances food-production gains against environmental costs.",
                },
                {
                    "question": "Which of the following is an environmental issue mentioned in the passage?",
                    "options": [
                        "A. Heavy use of chemical fertilizers",
                        "B. Shortage of musical instruments",
                        "C. Poor handwriting in schools",
                        "D. Delayed airport flights",
                    ],
                    "answer": "A",
                    "explanation": "Fertilizer pollution is the first environmental issue discussed.",
                },
            ]
        else:
            items = [
                {
                    "question": "Which statement best captures the main idea of the passage?",
                    "options": [
                        "A. The passage develops a central situation with supporting details.",
                        "B. The passage is mainly a list of unrelated chemical formulas.",
                        "C. The passage is mainly about computer networking.",
                        "D. The passage is mainly a sports fixture list.",
                    ],
                    "answer": "A",
                    "explanation": "Identify the controlling idea; all details support it.",
                },
                {
                    "question": (
                        "Which of the following best describes the writer's purpose in the passage?"
                    ),
                    "options": [
                        "A. To inform and explain a situation or idea.",
                        "B. To advertise a commercial product.",
                        "C. To write a personal diary entry.",
                        "D. To list scientific equations.",
                    ],
                    "answer": "A",
                    "explanation": (
                        "The writer presents information with supporting details, "
                        "which is characteristic of an informative/expository purpose."
                    ),
                },
                {
                    "question": (
                        "In the context of the passage, a word used to convey a "
                        "strong emotion or personal attitude is an example of _____."
                    ),
                    "options": [
                        "A. Loaded or emotive language",
                        "B. A mathematical symbol",
                        "C. Punctuation",
                        "D. A proper noun",
                    ],
                    "answer": "A",
                    "explanation": (
                        "Words chosen for emotional effect show the writer's attitude "
                        "and are called loaded or emotive language."
                    ),
                },
                {
                    "question": (
                        "A phrase that gives human qualities to a non-human subject "
                        "in the passage is an example of _____."
                    ),
                    "options": [
                        "A. Personification",
                        "B. Onomatopoeia",
                        "C. Alliteration",
                        "D. Hyperbole",
                    ],
                    "answer": "A",
                    "explanation": (
                        "Personification attributes human qualities to animals, "
                        "objects, or abstract ideas."
                    ),
                },
            ]

        for i, item in enumerate(items):
            out.append(
                {
                    "id": _qid("passage", subject, text[:60], item["question"]),
                    "subject": subject,
                    "exam_board": board,
                    "year": year,
                    "topic": "Comprehension",
                    "paper_type": "Comprehension",
                    "question": item["question"],
                    "passage": text,
                    "options": item["options"],
                    "answer": item["answer"],
                    "explanation": item["explanation"],
                    "images": [],
                    "source": f"{source}:q{i+1}",
                }
            )
    return out


def _from_seed_bank(subject: str) -> list[dict[str, Any]]:
    """Optional curated CBT MCQs (used to thicken thin subject banks such as English)."""
    path = RAW_DIR / subject.lower() / "cbt_mcq_bank.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for q in data:
        if not isinstance(q, dict):
            continue
        stem = str(q.get("question") or "").strip()
        opts = q.get("options") or []
        answer = _normalize_answer(q.get("answer"))
        topic = str(q.get("topic") or "General")
        if not _is_useful_mcq(stem, list(opts), answer, topic):
            continue
        norm_opts = []
        for i, opt in enumerate(list(opts)[:4]):
            letter = "ABCD"[i]
            text = str(opt).strip()
            if re.match(r"^[A-D][\).\:]", text, re.I):
                norm_opts.append(f"{letter}. {_clean_opt(text[2:])}")
            else:
                norm_opts.append(f"{letter}. {_clean_opt(text)}")
        out.append(
            {
                "id": _qid("seed", subject, stem),
                "subject": subject,
                "exam_board": str(q.get("exam_board") or "WAEC").upper(),
                "year": q.get("year"),
                "topic": topic,
                "paper_type": str(q.get("paper_type") or "Objective"),
                "question": stem,
                "passage": q.get("passage"),
                "options": norm_opts,
                "answer": answer,
                "explanation": str(q.get("explanation") or ""),
                "images": [],
                "source": f"cbt_mcq_bank:{subject}",
            }
        )
    return out


@lru_cache(maxsize=8)
def _unified_bank(subject: str) -> tuple[dict[str, Any], ...]:
    subject = subject.lower().strip()
    past = _from_past_json(subject)
    qa = _from_qa_json(subject)
    chunks = _from_chunks(subject)
    seed = _from_seed_bank(subject)
    # Keep items that already have answers; fill the rest from qa stems
    answered = [c for c in chunks if _is_letter_answer(c.get("answer"))]
    need = [c for c in chunks if not _is_letter_answer(c.get("answer"))]
    filled = _attach_answers_from_qa(need, subject)
    passages = _comprehension_passages(subject)
    merged = _dedupe(past + qa + answered + filled + seed + passages)
    _attach_qa_images(merged, subject)
    logger.info(
        "Exam bank %s: past=%d qa=%d chunk=%d seed=%d unique=%d with_images=%d passages=%d",
        subject,
        len(past),
        len(qa),
        len(answered) + len(filled),
        len(seed),
        len(merged),
        sum(1 for x in merged if x.get("images")),
        len(passages),
    )
    return tuple(merged)


def bank_stats(subject: str | None = None) -> dict[str, Any]:
    subjects = [subject] if subject else list(SUBJECTS)
    out: dict[str, Any] = {}
    for s in subjects:
        items = _unified_bank(s)
        by_board: dict[str, int] = {}
        for i in items:
            by_board[i["exam_board"]] = by_board.get(i["exam_board"], 0) + 1
        out[s] = {
            "total": len(items),
            "by_board": by_board,
            "with_images": sum(1 for i in items if i.get("images")),
        }
    return out


def _matches_board(item: dict[str, Any], exam: str) -> bool:
    board = exam.strip().upper()
    item_board = str(item.get("exam_board") or "").upper()
    if board == "JAMB":
        if item_board == "JAMB":
            return True
        # Allow WAEC/NECO objective as JAMB-style practice when JAMB pool thin
        return item.get("paper_type", "Objective") == "Objective"
    # Prefer exact board; fall back to any objective if pool would be tiny
    return item_board == board or item_board in {"WAEC", "NECO", "JAMB"}


def sample_questions(
    *,
    subject: str,
    exam: str = "WAEC",
    topic: str | None = None,
    n: int = 10,
    prefer_topics: list[str] | None = None,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    subject = subject.lower().strip()
    bank = list(_unified_bank(subject))
    exam_u = exam.strip().upper()

    exact = [q for q in bank if str(q.get("exam_board") or "").upper() == exam_u]
    if exam_u == "JAMB":
        pool = exact or [q for q in bank if _matches_board(q, exam_u)]
    else:
        pool = exact if len(exact) >= max(10, n // 2) else bank

    if topic:
        t = topic.lower()
        filtered = [q for q in pool if t in str(q.get("topic") or "").lower()]
        if filtered:
            pool = filtered

    if prefer_topics:
        preferred = [
            q
            for q in pool
            if any(p.lower() in str(q.get("topic") or "").lower() for p in prefer_topics if p)
        ]
        # Interleave prefer + rest, still unique
        rest = [q for q in pool if q not in preferred]
        pool = preferred + rest

    rng = random.Random(seed)
    rng.shuffle(pool)

    # Never repeat: take unique only up to available
    picked = pool[: max(1, min(n, len(pool)))]
    out: list[dict[str, Any]] = []
    for q in picked:
        out.append(
            {
                "id": q["id"],
                "subject": q["subject"],
                "exam_board": q["exam_board"],
                "jamb_style": exam_u == "JAMB" and q["exam_board"] != "JAMB",
                "year": q.get("year"),
                "topic": q.get("topic") or "General",
                "paper_type": q.get("paper_type") or "Objective",
                "question": q["question"],
                "passage": q.get("passage"),
                "options": q["options"],
                "answer": q["answer"],
                "explanation": q.get("explanation") or "",
                "images": q.get("images") or [],
                "source": q.get("source") or "",
            }
        )
    return out


def grade_choice(
    question: dict[str, Any],
    student_answer: str,
    *,
    language: str | None = None,
) -> dict[str, Any]:
    from app.i18n.messages import ui_string

    expected = _normalize_answer(question.get("answer"))
    given = _normalize_answer(student_answer)
    correct = bool(expected) and given.upper() == expected.upper()
    confused = None
    if not correct and question.get("topic"):
        confused = f"Needs review: {question.get('topic')}"
    return {
        "correct": correct,
        "expected": expected,
        "explanation": question.get("explanation") or "",
        "confused": confused,
        "feedback": (
            ui_string(
                "practice_correct",
                language,
                explanation=question.get("explanation")
                or ui_string("practice_correct_extra", language),
            )
            if correct
            else ui_string(
                "practice_wrong",
                language,
                expected=expected,
                explanation=question.get("explanation")
                or ui_string("practice_wrong_extra", language),
            )
        ),
    }


def reset_bank_cache() -> None:
    _load_qa.cache_clear()
    _load_chunks.cache_clear()
    load_subject.cache_clear()
    _unified_bank.cache_clear()
