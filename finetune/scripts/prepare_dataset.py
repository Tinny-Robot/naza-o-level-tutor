#!/usr/bin/env python3
"""Export curriculum instruction pairs for optional offline LoRA / QLoRA.

Reads ``data/eval/qa.json`` and writes JSONL under ``finetune/data/exports/``.
Stdlib only - safe to run without installing ``finetune/requirements.txt``.

Examples (from project root)::

    python finetune/scripts/prepare_dataset.py --limit 20 \\
        --out finetune/data/exports/sample_instruction_pairs.jsonl

    python finetune/scripts/prepare_dataset.py \\
        --out finetune/data/exports/full_instruction_pairs.jsonl

    python finetune/scripts/prepare_dataset.py --languages en ha --messages --limit 5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterator

EXPORT_VERSION = 1

SYSTEM_EN = (
    "You are Naza, a friendly eagle tutor for Nigerian O-Level (WAEC/NECO) "
    "students. Subjects include English Language, Mathematics, Physics, and "
    "Chemistry. Be accurate, clear, and exam-focused. Prefer concise "
    "explanations with worked steps for quantitative questions. Respond "
    "entirely in English using clear language suitable for an O-Level student. "
    "Keep necessary scientific or exam terms in their usual English form."
)

SYSTEM_HA = (
    "Kai Naza ne, malamin gaggafa na daliban O-Level (WAEC/NECO) na Najeriya. "
    "Ka koyar da Turanci, Lissafi, Physics, da Chemistry. Ka bayyana da Hausa "
    "mai sauƙi daidai da manhaja. Kada ka canza zuwa Turanci sai dai idan "
    "kalmar kimiyya ko jarabawa tana buƙatar Turanci don fahimta. Ka kasance "
    "daidai; idan ba ka da tabbaci, faɗi haka."
)


def _project_root() -> Path:
    # finetune/scripts/this_file.py -> repo root
    return Path(__file__).resolve().parents[2]


def _load_qa(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"QA dataset not found: {path}")
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list in {path}")
    return data


def _pick_answer(item: dict[str, Any]) -> str:
    for key in ("answer", "explanation"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _hausa_scaffold(output_en: str) -> str:
    """Honest placeholder: keep English facts; mark need for Hausa annotation."""
    return (
        "[HAUSA_ANNOTATION_NEEDED] Bayyana amsar da ke ƙasa da Hausa mai sauƙi "
        "ga ɗalibin O-Level, ka kiyaye kalmomin kimiyya a Turanci idan ya cancanta.\n\n"
        f"{output_en}"
    )


def _record_for_language(
    item: dict[str, Any],
    language: str,
    *,
    include_messages: bool,
) -> dict[str, Any] | None:
    question = str(item.get("question") or "").strip()
    output_en = _pick_answer(item)
    if not question or not output_en:
        return None

    source_id = str(item.get("id") or "").strip() or "unknown"
    subject = str(item.get("subject") or "").strip() or "unknown"
    topic = item.get("topic")
    question_type = item.get("question_type")

    if language == "en":
        system = SYSTEM_EN
        output = output_en
        output_ha = None
        hausa_status = "n/a"
    elif language == "ha":
        system = SYSTEM_HA
        output_ha = None
        output = _hausa_scaffold(output_en)
        hausa_status = "scaffold"
    else:
        raise ValueError(f"Unsupported language: {language}")

    record: dict[str, Any] = {
        "id": f"{source_id}-{language}",
        "source": "data/eval/qa.json",
        "source_id": source_id,
        "subject": subject,
        "topic": topic,
        "question_type": question_type,
        "language": language,
        "system": system,
        "instruction": question,
        "output": output,
        "output_en": output_en,
        "output_ha": output_ha,
        "meta": {
            "export_version": EXPORT_VERSION,
            "hausa_status": hausa_status,
            "expected_keywords": item.get("expected_keywords") or [],
            "needs_review": bool(item.get("needs_review")),
        },
    }

    if include_messages:
        record["messages"] = [
            {"role": "system", "content": system},
            {"role": "user", "content": question},
            {"role": "assistant", "content": output},
        ]

    return record


def iter_records(
    items: list[dict[str, Any]],
    languages: list[str],
    *,
    include_messages: bool,
    limit: int | None,
) -> Iterator[dict[str, Any]]:
    written = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        for language in languages:
            record = _record_for_language(
                item, language, include_messages=include_messages
            )
            if record is None:
                continue
            yield record
            written += 1
            if limit is not None and written >= limit:
                return


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    root = _project_root()
    parser = argparse.ArgumentParser(
        description=(
            "Export Naza curriculum Q&A to instruction JSONL for optional "
            "offline LoRA/QLoRA (does not affect production GGUF)."
        )
    )
    parser.add_argument(
        "--qa",
        type=Path,
        default=root / "data" / "eval" / "qa.json",
        help="Path to qa.json (default: data/eval/qa.json)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=root / "finetune" / "data" / "exports" / "sample_instruction_pairs.jsonl",
        help="Output JSONL path",
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        default=["en", "ha"],
        choices=["en", "ha"],
        help="Target languages to emit (default: en ha)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of output records (not source items)",
    )
    parser.add_argument(
        "--messages",
        action="store_true",
        help="Include a chat-style messages[] array on each record",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    items = _load_qa(args.qa)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    subjects: set[str] = set()
    with args.out.open("w", encoding="utf-8") as fh:
        for record in iter_records(
            items,
            list(args.languages),
            include_messages=args.messages,
            limit=args.limit,
        ):
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
            subjects.add(str(record.get("subject") or ""))

    print(f"Wrote {count} records -> {args.out}")
    print(f"Source items available: {len(items)}")
    print(f"Languages: {', '.join(args.languages)}")
    print(f"Subjects seen: {', '.join(sorted(s for s in subjects if s)) or '(none)'}")
    print(
        "Note: Hausa rows use an annotation scaffold when output_ha is empty; "
        "they are not fabricated fluent translations."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
