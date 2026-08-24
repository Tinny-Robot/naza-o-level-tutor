# Training artifacts (gitignored weights)

Runs and checkpoints belong here when an operator actually trains.

- `adapters/` - PEFT adapter slot (see README there). **Not** loaded by production.
- Other run dirs / optimizer states / logs should stay local (gitignored).

Do not commit fabricated metrics, wandb export zips, or placeholder `.safetensors`
files that pretend a full train completed.
