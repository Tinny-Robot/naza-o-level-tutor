# Inference benchmark: mmap_context_4096

- Scope: **pilot** (1 of 1681 questions)
- Configuration: Mmap with F16 KV and controlled 4096 context
- Accuracy (mean expected-keyword recall): 0.375
- Exact match: 0.000
- Peak RSS: 8.497 GiB
- RAM headroom against 7 GiB: -1.497 GiB
- Status: **FAIL - ABOVE COMPETITION LIMIT**
- Average generation speed: 4.535 tok/s
- Average prompt speed: 27.706 tok/s
- Average TTFT: 89.816 s
- Average latency: 203.940 s
- Model load time: 5.397 s

## Configuration

```json
{
  "name": "mmap_context_4096",
  "description": "Mmap with F16 KV and controlled 4096 context",
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
| chemistry-past_questions-003-8ebd4ce5 | 0.375 | 4.535 | 27.706 | 89.816 | 203.940 |  |
