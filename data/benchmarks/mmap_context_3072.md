# Inference benchmark: mmap_context_3072

- Scope: **pilot** (1 of 1681 questions)
- Configuration: Mmap with F16 KV and controlled 3072 context
- Accuracy (mean expected-keyword recall): 0.375
- Exact match: 0.000
- Peak RSS: 8.478 GiB
- RAM headroom against 7 GiB: -1.478 GiB
- Status: **FAIL - ABOVE COMPETITION LIMIT**
- Average generation speed: 4.435 tok/s
- Average prompt speed: 27.115 tok/s
- Average TTFT: 91.779 s
- Average latency: 208.413 s
- Model load time: 5.798 s

## Configuration

```json
{
  "name": "mmap_context_3072",
  "description": "Mmap with F16 KV and controlled 3072 context",
  "n_ctx": 3072,
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
| chemistry-past_questions-003-8ebd4ce5 | 0.375 | 4.435 | 27.115 | 91.779 | 208.413 |  |
