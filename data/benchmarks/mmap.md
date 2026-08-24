# Inference benchmark: mmap

- Scope: **pilot** (1 of 1681 questions)
- Configuration: Mmap enabled and mlock disabled; identical to current production
- Accuracy (mean expected-keyword recall): 0.375
- Exact match: 0.000
- Peak RSS: 8.498 GiB
- RAM headroom against 7 GiB: -1.498 GiB
- Status: **FAIL - ABOVE COMPETITION LIMIT**
- Average generation speed: 4.402 tok/s
- Average prompt speed: 25.044 tok/s
- Average TTFT: 99.361 s
- Average latency: 216.925 s
- Model load time: 6.885 s

## Configuration

```json
{
  "name": "mmap",
  "description": "Mmap enabled and mlock disabled; identical to current production",
  "n_ctx": 4096,
  "use_mmap": true,
  "use_mlock": false,
  "type_k": "F16",
  "type_v": "F16",
  "n_batch": 512,
  "n_ubatch": 512
}
```

## Per-question results

| ID | Accuracy | Gen tok/s | Prompt tok/s | TTFT | Latency | Error |
|---|---:|---:|---:|---:|---:|---|
| chemistry-past_questions-003-8ebd4ce5 | 0.375 | 4.402 | 25.044 | 99.361 | 216.925 |  |
