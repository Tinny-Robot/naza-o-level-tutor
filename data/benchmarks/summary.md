# ADTC inference optimization comparison

Scope: **pilot**, 1 questions from the unchanged evaluation file.

| Configuration | Accuracy | Peak RSS | RAM Headroom | Gen tok/s | Prompt tok/s | TTFT | Avg Latency | ADTC score | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| baseline | 0.375 | 8.497 GiB | -1.497 GiB | 4.900 | 30.507 | 81.570 s | 187.282 s | 45.502 | FAIL - ABOVE COMPETITION LIMIT |
| mmap | 0.375 | 8.498 GiB | -1.498 GiB | 4.402 | 25.044 | 99.361 s | 216.925 s | 42.783 | FAIL - ABOVE COMPETITION LIMIT |
| mmap_kv | 0.125 | 8.452 GiB | -1.452 GiB | 5.175 | 23.108 | 107.698 s | 125.659 s | 34.503 | FAIL - ABOVE COMPETITION LIMIT |
| mmap_kv_q4 | 0.125 | 8.418 GiB | -1.418 GiB | 5.291 | 24.693 | 100.774 s | 128.481 s | 35.135 | FAIL - ABOVE COMPETITION LIMIT |
| mmap_context_4096 | 0.375 | 8.497 GiB | -1.497 GiB | 4.535 | 27.706 | 89.816 s | 203.940 s | 43.509 | FAIL - ABOVE COMPETITION LIMIT |
| mmap_context_3072 | 0.375 | 8.478 GiB | -1.478 GiB | 4.435 | 27.115 | 91.779 s | 208.413 s | 42.965 | FAIL - ABOVE COMPETITION LIMIT |
| mmap_context_2048 | 0.000 | 8.345 GiB | -1.345 GiB | 0.000 | n/a | n/a s | 0.651 s | 0.000 | FAIL - ABOVE COMPETITION LIMIT |
| best | 0.125 | 8.419 GiB | -1.419 GiB | 5.495 | 24.688 | 100.794 s | 127.472 s | 36.250 | FAIL - ABOVE COMPETITION LIMIT |

The ADTC-oriented score uses 50% keyword accuracy, 30% speed normalized to the fastest measured configuration, and 20% positive headroom under 7 GiB.
