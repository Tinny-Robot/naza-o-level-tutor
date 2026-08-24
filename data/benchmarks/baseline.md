# Inference benchmark: baseline

- Scope: **pilot** (1 of 1681 questions)
- Configuration: Current production llama.cpp defaults made explicit
- Accuracy (mean expected-keyword recall): 0.375
- Exact match: 0.000
- Peak RSS: 8.497 GiB
- RAM headroom against 7 GiB: -1.497 GiB
- Status: **FAIL - ABOVE COMPETITION LIMIT**
- Average generation speed: 4.900 tok/s
- Average prompt speed: 30.507 tok/s
- Average TTFT: 81.570 s
- Average latency: 187.282 s
- Model load time: 5.093 s

## Configuration

```json
{
  "name": "baseline",
  "description": "Current production llama.cpp defaults made explicit",
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
| chemistry-past_questions-003-8ebd4ce5 | 0.375 | 4.900 | 30.507 | 81.570 | 187.282 |  |
