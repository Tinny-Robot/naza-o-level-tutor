#!/usr/bin/env python3
"""Skeleton entrypoint for optional offline LoRA / QLoRA training.

Production Naza does **not** call this script. Training deps live only in
``finetune/requirements.txt`` and must not be added to the app ``pyproject.toml``.

Usage (separate venv on a GPU machine)::

    python -m venv .venv-finetune && source .venv-finetune/bin/activate
    pip install -r finetune/requirements.txt
    python finetune/scripts/prepare_dataset.py \\
        --out finetune/data/exports/full_instruction_pairs.jsonl
    python finetune/scripts/train_lora.py \\
        --config finetune/configs/lora_hausa_curriculum.yaml

This skeleton validates the config, prints the intended PEFT recipe, and exits
without inventing metrics or writing fake adapter weights. Pass ``--execute``
only after deps are installed; even then the trainer body is intentionally
minimal and will raise ``NotImplementedError`` until you wire a real TRL/PEFT
loop for your hardware.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "PyYAML is required to read the config. Install finetune deps in a "
            "separate venv:\n"
            "  pip install -r finetune/requirements.txt\n"
            f"Missing import: {exc}"
        ) from exc

    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a mapping: {path}")
    return data


def _print_plan(cfg: dict[str, Any], config_path: Path) -> None:
    run = cfg.get("run") or {}
    model = cfg.get("model") or {}
    data = cfg.get("data") or {}
    lora = cfg.get("lora") or {}
    training = cfg.get("training") or {}

    print("=== Naza offline LoRA/QLoRA plan (not production launch) ===")
    print(f"config:           {config_path}")
    print(f"run.name:         {run.get('name')}")
    print(f"base_model:       {model.get('base_model')}")
    print(f"load_in_4bit:     {model.get('load_in_4bit')}")
    print(f"train_file:       {data.get('train_file')}")
    print(f"adapter_dir:      {run.get('adapter_dir')}")
    print(f"lora.r / alpha:   {lora.get('r')} / {lora.get('lora_alpha')}")
    print(f"epochs:           {training.get('num_train_epochs')}")
    print(f"lr:               {training.get('learning_rate')}")
    print()
    print("Intended steps when --execute is fully wired on a GPU host:")
    print("  1. Load base instruct checkpoint (HF), not the production GGUF.")
    print("  2. Attach PEFT LoRA (or QLoRA via bitsandbytes).")
    print("  3. Map JSONL fields system/instruction/output -> chat messages.")
    print("  4. Train with TRL SFTTrainer (or equivalent).")
    print("  5. Save adapter under finetune/artifacts/adapters/ (gitignored).")
    print("  6. Evaluate offline; do not change launch.sh / MODEL_PATH.")
    print()
    print(
        "Production reminder: ./launch.sh continues to use the base GGUF + RAG. "
        "Adapters here are never auto-loaded."
    )


def _execute_stub(cfg: dict[str, Any]) -> None:
    """Refuse to pretend training finished; document the hook for operators."""
    missing = []
    for pkg in ("torch", "transformers", "peft", "trl", "datasets"):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        raise SystemExit(
            "Cannot --execute: missing training packages "
            f"{missing}. Use a separate venv and "
            "`pip install -r finetune/requirements.txt`."
        )

    train_file = Path(str((cfg.get("data") or {}).get("train_file") or ""))
    if not train_file.is_file():
        raise SystemExit(
            f"Train file not found: {train_file}. Run prepare_dataset.py first."
        )

    raise NotImplementedError(
        "train_lora.py is an honest skeleton: PEFT/TRL training is not bundled "
        "into the production app. Implement the SFT loop here on a GPU machine "
        "(see finetune/README.md), then write real adapters under "
        "finetune/artifacts/adapters/. Do not commit fabricated metrics or "
        "placeholder weight binaries that claim a completed train."
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    root = _project_root()
    parser = argparse.ArgumentParser(
        description="Optional offline LoRA/QLoRA training skeleton for Naza."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=root / "finetune" / "configs" / "lora_hausa_curriculum.yaml",
        help="YAML hyperparameter template",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help=(
            "Attempt the training hook (requires finetune deps). "
            "Currently raises NotImplementedError after dependency checks."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.config.is_file():
        print(f"Error: config not found: {args.config}", file=sys.stderr)
        return 1

    try:
        cfg = _load_yaml(args.config)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        print(
            f"Config file is present at {args.config} "
            "(open it directly for hyperparameters).",
            file=sys.stderr,
        )
        return 2

    _print_plan(cfg, args.config)

    if args.execute:
        _execute_stub(cfg)

    print("Dry-run complete (no weights written).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except NotImplementedError as exc:
        print(f"Refusing fake train: {exc}", file=sys.stderr)
        raise SystemExit(3) from exc
