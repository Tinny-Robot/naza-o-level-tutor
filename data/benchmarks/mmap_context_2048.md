# Inference benchmark: mmap_context_2048

- Scope: **pilot** (1 of 1681 questions)
- Configuration: Mmap with F16 KV and controlled 2048 context
- Accuracy (mean expected-keyword recall): 0.000
- Exact match: 0.000
- Peak RSS: 8.345 GiB
- RAM headroom against 7 GiB: -1.345 GiB
- Status: **FAIL - ABOVE COMPETITION LIMIT**
- Average generation speed: n/a tok/s
- Average prompt speed: n/a tok/s
- Average TTFT: n/a s
- Average latency: 0.651 s
- Model load time: 5.183 s

## Configuration

```json
{
  "name": "mmap_context_2048",
  "description": "Mmap with F16 KV and controlled 2048 context",
  "n_ctx": 2048,
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
| chemistry-past_questions-003-8ebd4ce5 | 0.000 | n/a | n/a | n/a | 0.651 | ValueError: Requested tokens (2488) exceed context window of 2048 |
