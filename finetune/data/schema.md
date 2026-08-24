# Fine-tune instruction-pair schema

Records are **JSON Lines** (one JSON object per line). Source of truth for
automated export is `data/eval/qa.json` (curriculum-aligned Q&A used also by
retrieval evaluation). Optional Hausa fields support bilingual adaptation
without requiring completed translations in-repo.

## Record fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | yes | Stable id (usually the QA id + language suffix) |
| `source` | string | yes | e.g. `data/eval/qa.json` |
| `source_id` | string | yes | Original QA item id |
| `subject` | string | yes | `chemistry` \| `physics` \| `mathematics` \| `english` |
| `topic` | string | no | Syllabus topic string from QA |
| `question_type` | string | no | e.g. `theory` |
| `language` | string | yes | `en` or `ha` (target assistant language) |
| `system` | string | yes | Tutor system prompt for that language |
| `instruction` | string | yes | Student-facing question / prompt |
| `output` | string | yes | Primary assistant target for training |
| `output_en` | string | yes | English reference answer (always filled from QA) |
| `output_ha` | string \| null | no | Hausa reference; `null` until annotated |
| `meta` | object | no | Keywords, needs_review, export version |

## Language policy

- **`language: en`**: `output` equals `output_en`.
- **`language: ha`**: `output` prefers `output_ha` when present; otherwise the
  exporter writes a **scaffolding** string that keeps `output_en` as the
  factual backbone and marks the row as needing Hausa annotation (honest -
  not a fake fluent translation).

Scientific / exam terms may remain in English inside Hausa answers (same rule
as `app/i18n/language.py`).

## Example (`en`)

```json
{
  "id": "chemistry-...-en",
  "source": "data/eval/qa.json",
  "source_id": "chemistry-...",
  "subject": "chemistry",
  "topic": "Acids, Bases & Salts",
  "question_type": "theory",
  "language": "en",
  "system": "You are Naza...",
  "instruction": "Classify salts into five main groups...",
  "output": "Salts: Normal (NaCl), ...",
  "output_en": "Salts: Normal (NaCl), ...",
  "output_ha": null,
  "meta": {"export_version": 1, "hausa_status": "n/a"}
}
```

## Chat-format mapping (for TRL / Axolotl-style trainers)

Trainers that expect `messages` can map:

1. `{role: system, content: record.system}`
2. `{role: user, content: record.instruction}`
3. `{role: assistant, content: record.output}`

`scripts/prepare_dataset.py` can also emit an optional `messages` array when
`--messages` is passed.

## Files

- `exports/sample_instruction_pairs.jsonl` - small committed sample for judges
- `exports/*.jsonl` - full dumps are gitignored; regenerate with the prepare script
