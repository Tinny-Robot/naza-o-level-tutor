# Inference benchmark: best

- Scope: **pilot** (1 of 1681 questions)
- Configuration: Measured best combined mmap, quantized KV, and controlled context
- Accuracy (mean expected-keyword recall): 0.125
- Exact match: 0.000
- Peak RSS: 8.419 GiB
- RAM headroom against 7 GiB: -1.419 GiB
- Status: **FAIL - ABOVE COMPETITION LIMIT**
- Average generation speed: 5.495 tok/s
- Average prompt speed: 24.688 tok/s
- Average TTFT: 100.794 s
- Average latency: 127.472 s
- Model load time: 5.052 s

## Configuration

```json
{
  "name": "best",
  "description": "Measured best combined mmap, quantized KV, and controlled context",
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
| chemistry-past_questions-003-8ebd4ce5 | 0.125 | 5.495 | 24.688 | 100.794 | 127.472 |  |
