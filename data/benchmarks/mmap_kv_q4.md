# Inference benchmark: mmap_kv_q4

- Scope: **pilot** (1 of 1681 questions)
- Configuration: Mmap with aggressive Q4_0 K/V cache
- Accuracy (mean expected-keyword recall): 0.125
- Exact match: 0.000
- Peak RSS: 8.418 GiB
- RAM headroom against 7 GiB: -1.418 GiB
- Status: **FAIL - ABOVE COMPETITION LIMIT**
- Average generation speed: 5.291 tok/s
- Average prompt speed: 24.693 tok/s
- Average TTFT: 100.774 s
- Average latency: 128.481 s
- Model load time: 5.214 s

## Configuration

```json
{
  "name": "mmap_kv_q4",
  "description": "Mmap with aggressive Q4_0 K/V cache",
  "n_ctx": 4096,
  "use_mmap": true,
  "use_mlock": false,
  "type_k": "Q4_0",
  "type_v": "Q4_0",
  "n_batch": 512,
  "n_ubatch": 512
}
```

## Per-question results

| ID | Accuracy | Gen tok/s | Prompt tok/s | TTFT | Latency | Error |
|---|---:|---:|---:|---:|---:|---|
| chemistry-past_questions-003-8ebd4ce5 | 0.125 | 5.291 | 24.693 | 100.774 | 128.481 |  |
