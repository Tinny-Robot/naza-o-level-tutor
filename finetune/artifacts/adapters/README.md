# Adapter weights (optional offline use)

Place trained LoRA / QLoRA adapters in this directory after a real training
run, for example:

```
finetune/artifacts/adapters/lora_hausa_curriculum/
  adapter_config.json
  adapter_model.safetensors
```

## Production does not auto-load these

- `./launch.sh`, Docker Compose, and `app/generation/llm.py` load only the
  configured base GGUF under `models/`.
- Nothing in this folder is mounted or referenced by default inference.
- Keeping adapters here is for offline inspection and operator-driven
  experiments (merge-to-GGUF / PEFT load outside the stock launch path).

Weight files and checkpoints are gitignored. This README and `.gitkeep` stay
in git so the slot is visible to judges without shipping binaries.
