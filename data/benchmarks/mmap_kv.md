# Inference benchmark: mmap_kv

- Scope: **pilot** (1 of 1681 questions)
- Configuration: Mmap with Q8_0 K/V cache
- Accuracy (mean expected-keyword recall): 0.125
- Exact match: 0.000
- Peak RSS: 8.452 GiB
- RAM headroom against 7 GiB: -1.452 GiB
- Status: **FAIL - ABOVE COMPETITION LIMIT**
- Average generation speed: 5.175 tok/s
- Average prompt speed: 23.108 tok/s
- Average TTFT: 107.698 s
- Average latency: 125.659 s
- Model load time: 5.612 s

## Configuration

```json
{
  "name": "mmap_kv",
  "description": "Mmap with Q8_0 K/V cache",
  "n_ctx": 4096,
  "use_mmap": true,
  "use_mlock": false,
  "type_k": "Q8_0",
  "type_v": "Q8_0",
  "n_batch": 512,
  "n_ubatch": 512
}
```

## Per-question results

| ID | Accuracy | Gen tok/s | Prompt tok/s | TTFT | Latency | Error |
|---|---:|---:|---:|---:|---:|---|
| chemistry-past_questions-003-8ebd4ce5 | 0.125 | 5.175 | 23.108 | 107.698 | 125.659 |  |
