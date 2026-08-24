# llama.cpp CPU repack memory investigation

Date: 2026-08-12

Scope: source and model inspection only. No production configuration, model file, prompt, RAG index, or evaluation question was changed.

## Executive summary

The measured 2,165.62 MiB `CPU_REPACK` allocation is an exact second representation of all 253 `Q4_K` tensors in the current GGUF. The installed AVX2 build selects the CPU repack buffer for every one of those tensors.

With mmap enabled, llama.cpp keeps a file-backed mapping covering the GGUF tensor region. Loading a repacked tensor reads its Q4_K bytes from that mapping and writes a transformed copy into a separate anonymous CPU buffer. The source pages are file-backed and kernel-reclaimable, but this commit does not issue `MADV_DONTNEED` or unmap interior repacked tensor ranges after conversion. Immediately after load, both representations can therefore count toward RSS.

The most promising supported experiment is not no-repack. It is:

1. Keep `use_extra_bufts=true`, preserving CPU_REPACK and its optimized kernels.
2. Set `use_mmap=false`, or use supported direct I/O where available.
3. Load repacked tensors through the temporary read buffer, so their original Q4_K source bytes are not retained as a long-lived mapping.

Source accounting predicts a steady model-weight allocation near 4,731.51 MiB instead of 6,897.13 MiB. A temporary read buffer can add up to 360 MiB during loading because `token_embd.weight` is the largest repacked tensor. This is a hypothesis from the exact allocation path, not benchmark evidence. It must be tested in an isolated A/B benchmark before any recommendation.

## Installed source verification

- `llama-cpp-python`: `0.3.34`
- Python tag: `v0.3.34`
- Bundled llama.cpp submodule: `e3546c7948e3af463d0b401e6421d5a4c2faf565`
- Installed CPU features: SSE3, SSSE3, AVX, AVX2, F16C, FMA, BMI2, AVX512, OpenMP, and REPACK
- Backend: CPU-only

The official `llama-cpp-python` tag pins `vendor/llama.cpp` to the same commit reported by the installed runtime.

## Phase 1: llama.cpp allocation path

### 1. GGUF file mapping

Relevant source:

- `src/llama-model-loader.cpp`, `llama_model_loader::init_mappings`, lines 1342-1366
- `src/llama-mmap.cpp`, `llama_mmap::impl`, lines 441-476
- `src/llama-model.cpp`, model buffer creation, lines 1527-1562

When mmap is enabled:

- The loader creates a read-only `MAP_SHARED` mapping for the GGUF.
- The mapping may be prefetched with `MAP_POPULATE` and `POSIX_MADV_WILLNEED`.
- The default CPU buffer is created from a pointer into the mapped file.
- Tensors assigned to the normal CPU buffer point directly into the file-backed mapping.

The mapped tensor region measured by llama.cpp is 4,731.51 MiB, equal to the total bytes of all 720 tensor payloads.

### 2. CPU_REPACK buffer selection

Relevant source:

- `src/llama-model.cpp`, `make_cpu_buft_list`, lines 871-923
- `src/llama-model-loader.cpp`, `select_weight_buft` and tensor creation, lines 1054-1219
- `ggml/src/ggml-cpu/ggml-cpu.cpp`, `ggml_backend_cpu_device_get_extra_buffers_type`
- `ggml/src/ggml-cpu/repack.cpp`, `ggml_repack_get_optimal_repack_type`, lines 4528-4724

`make_cpu_buft_list` places extra CPU buffer types before the ordinary CPU buffer when `use_extra_bufts=true`. The tensor loader tests buffer compatibility and assigns eligible weight tensors to `CPU_REPACK`.

On this installed x86 build:

- AVX2 makes `Q4_0` eligible when row count is divisible by 8.
- AVX2 makes `Q4_K` eligible when row count is divisible by 8.
- AVX512 makes `Q2_K` eligible when row count is divisible by 8.
- AVX2 makes `IQ4_NL` and `MXFP4` eligible when row count is divisible by 8.
- In this commit, x86 does not select the repack buffer for `Q5_K`, `Q6_K`, or `Q8_0`; those branches are implemented for other CPU feature paths.

The current GGUF contains only one x86-eligible repack type: `Q4_K`. All 253 Q4_K tensors satisfy the row divisibility condition.

### 3. Repack allocation and conversion

Relevant source:

- `ggml/src/ggml-cpu/repack.cpp`, `ggml_backend_cpu_repack_buffer_type_alloc_buffer`, lines 4751-4763
- `ggml/src/ggml-cpu/repack.cpp`, `ggml_backend_cpu_repack_buffer_set_tensor`, lines 4733-4743
- `src/llama-model-loader.cpp`, `llama_model_loader::load_all_data`, lines 1530-1572

The repack buffer allocator calls the normal CPU allocator, then changes the buffer type to `CPU_REPACK`. This is anonymous writable memory.

For each repacked tensor with mmap enabled:

1. `data` points at the tensor bytes in the mapped GGUF.
2. `ggml_backend_tensor_set` invokes the CPU_REPACK `set_tensor` callback.
3. The callback transforms the source layout into the separately allocated repack destination.

The destination size uses normal `ggml_nbytes`, so the repacked copy is the same byte size as the original quantized tensor payload. It is a layout transformation, not an additional quantization level.

### 4. Exact duplicated representation

All Q4_K tensors:

- Count: 253
- Elements: 4,037,017,600
- Bytes: 2,270,822,400
- Memory: 2,165.625 MiB, 2.115 GiB

This exactly matches the measured `CPU_REPACK` model buffer of approximately 2,165.62 MiB.

Repacked Q4_K groups:

| Group | Tensors | Repacked MiB |
|---|---:|---:|
| FFN gate | 42 | 590.625 |
| FFN up | 42 | 590.625 |
| Token embedding / tied output | 1 | 360.000 |
| FFN down | 21 | 295.313 |
| Attention output | 42 | 137.813 |
| Attention Q | 42 | 137.813 |
| Attention K | 42 | 34.453 |
| Attention V | 21 | 18.984 |
| **Total** | **253** | **2,165.625** |

The 360 MiB `token_embd.weight` tensor is also used as the tied output matrix when a separate output tensor is absent, so disabling its repack may affect generation performance as well as loading memory.

### 5. Why the mapped source remains

Relevant source:

- `src/llama-model-loader.cpp`, final mmap cleanup, lines 1676-1688
- `src/llama-model.cpp`, mapping ownership transfer, lines 1634-1637
- `src/llama-mmap.cpp`, `unmap_fragment`, lines 490-520

The model still needs the mapping for every tensor that remains in the normal CPU buffer, including the very large Q5_K tensor, Q6_K tensors, F32 tensors, and BF16 tensor.

The loader tracks the first and last mapped bytes used by each context. It unmaps only unused prefixes and suffixes. It does not unmap arbitrary interior ranges belonging to repacked tensors. The mapping object is then transferred to the model and kept alive.

The repacked tensors themselves no longer need their original bytes for inference after conversion. The reason their source mapping remains addressable is the shared contiguous GGUF mapping and the absence of per-tensor interior unmapping or post-conversion page advice in this commit.

### 6. File-backed versus anonymous memory

- Original GGUF tensor bytes: read-only, `MAP_SHARED`, file-backed.
- CPU_REPACK destination: writable, anonymous CPU allocation.
- Compute and KV buffers: separate anonymous allocations.

The original pages do not have to stay physically resident forever. Linux can evict clean file-backed pages under pressure and fault them back from storage. However, repacking reads every eligible Q4_K source page, making those pages resident during model load. Peak RSS can therefore include both the mapped source and anonymous repack copy.

This llama.cpp commit uses `POSIX_MADV_WILLNEED` for prefetch and `POSIX_MADV_RANDOM` for NUMA cases. It does not use `MADV_DONTNEED` or `POSIX_FADV_DONTNEED` after repacking.

### 7. Supported ways to control duplicate residency

#### A. Disable mmap while keeping repack enabled

Relevant source:

- `src/llama-model-loader.cpp`, non-mmap loading path, lines 1573-1646

With `use_mmap=false`, normal CPU tensors are read directly into their allocated CPU buffers. CPU_REPACK tensors are read into a temporary `read_buf`, transformed into the repack destination, and the source buffer is not retained after loading.

Expected persistent weight buffers from source accounting:

| Buffer | MiB |
|---|---:|
| Non-repacked tensor payloads | 2,565.881 |
| CPU_REPACK Q4_K payloads | 2,165.625 |
| **Persistent tensor total** | **4,731.506** |

The largest repacked tensor is 360 MiB, so the temporary read buffer may raise model-load peak by approximately 360 MiB. Load time and storage I/O behavior may also change.

Using the measured 8.526 GiB production peak as a rough base, subtracting the duplicated Q4_K mapped residency gives approximately 6.41 GiB steady RSS. Including a possible 360 MiB load staging peak gives approximately 6.76 GiB. These are estimates, not measurements.

This path retains the CPU_REPACK representation and optimized inference kernels. It is the highest-priority next benchmark.

#### B. Direct I/O with repack enabled

`use_direct_io=true` disables mmap when the filesystem supports direct I/O. It reaches the same non-mmap tensor-loading logic, with stricter alignment and different I/O behavior. It is supported but should be tested only after the simpler `use_mmap=false` case.

#### C. Per-tensor buffer overrides

The llama.cpp C API supports `llama_model_tensor_buft_override`, and the CLI supports `--override-tensor <pattern>=<buffer-type>`. A selected tensor can be forced to the normal CPU buffer while other eligible tensors remain repacked.

This could create a controlled memory/performance curve instead of the all-or-nothing `use_extra_bufts=false` result. For example, avoiding repack for selected Q4_K groups would save exactly their repack allocation size.

Limitations in the installed Python binding:

- `llama-cpp-python 0.3.34` declares `tensor_buft_overrides` as a `c_void_p` marked unused.
- The high-level `Llama` constructor does not expose a supported tensor override argument.
- An isolated low-level ctypes or llama.cpp CLI harness would be required for a fair experiment.

#### D. Disable all extra buffers

`use_extra_bufts=false`, exposed in the CLI as `--no-repack`, is the supported global repack disable. It is not the only supported memory control, but it is the only global switch for all CPU extra buffers. The completed A/B benchmark showed that this path is not acceptable for the current application.

#### E. Options that do not solve this duplication

- `no_host` concerns device host buffers and does not remove CPU_REPACK duplication in this CPU-only setup.
- KV cache types and context length do not materially affect the 2.166 GiB repack allocation.
- Batch and ubatch change compute buffers, not the persistent repack representation.
- mmap alone cannot guarantee low RSS after repack because the repack operation touches the source pages.

## Phase 2: exact GGUF inspection

### Model identity

| Property | Value |
|---|---|
| Filename | `models/gemma-4-E4B-it-Q4_K_M.gguf` |
| File size | 4,977,171,584 bytes, 4,746.601 MiB, 4.635 GiB |
| Tensor payload | 4,961,343,656 bytes, 4,731.506 MiB |
| Metadata/alignment overhead | 15,827,928 bytes |
| Architecture | `gemma4` |
| Name | `Gemma-4-E4B-It` |
| File type | 15, `MOSTLY_Q4_K_M` / Q4_K Medium |
| Quantization version | 2 |
| Quantized by | Unsloth |
| Importance matrix | 141 chunks, 342 entries |
| Parameters | 7,518,069,290, approximately 7.518B |
| Effective tensor bits per weight | 5.279 |
| Tensor count | 720 |
| Native model context | 131,072 |
| Transformer blocks | 42 |

### Per-type tensor distribution

| Tensor type | Count | Elements | Payload MiB | Repacked on this x86 build |
|---|---:|---:|---:|---|
| Q4_K | 253 | 4,037,017,600 | 2,165.625 | Yes, all 253 |
| Q5_K | 1 | 2,818,572,288 | 1,848.000 | No |
| Q6_K | 42 | 579,338,240 | 453.223 | No |
| F32 | 423 | 55,616,042 | 212.158 | No |
| BF16 | 1 | 27,525,120 | 52.500 | No |

### Largest tensors

| Tensor | Type | Shape | Payload MiB | Repacked |
|---|---|---|---:|---|
| `per_layer_token_embd.weight` | Q5_K | 10752 x 262144 | 1,848.000 | No |
| `token_embd.weight` | Q4_K | 2560 x 262144 | 360.000 | Yes |
| `per_layer_model_proj.weight` | BF16 | 2560 x 10752 | 52.500 | No |
| Each selected `ffn_down.weight` | Q6_K | 10240 x 2560 | 20.508 | No |
| Each Q4_K FFN matrix | Q4_K | 2560 x 10240 or reverse | 14.063 | Yes |

The single Q5_K `per_layer_token_embd.weight` tensor accounts for approximately 39.1% of all tensor payload bytes and is not CPU-repacked on this x86 build. It is the largest mapped-only weight allocation.

### Is Q4_K_M the minimum-memory suitable quantization?

No. Q4_K_M is a quality-oriented medium 4-bit family quantization, not the smallest supported GGUF representation. Lower-bit families can reduce model bytes further, but may reduce quality, change CPU kernel behavior, or create a different repack profile.

The current file is internally mixed rather than uniform Q4:

- The largest tensor is Q5_K.
- 42 large FFN down tensors are Q6_K.
- Normalization and other small tensors remain F32.
- One projection tensor is BF16.

This mixed layout is consistent with a quality-preserving importance-matrix quantization. It is not possible to call a lower-bit variant suitable without the same controlled accuracy and speed evaluation used for no-repack.

### Local model inventory

Only one GGUF model exists under `/home/ubuntu`:

`/home/ubuntu/O-Level/O-Level/models/gemma-4-E4B-it-Q4_K_M.gguf`

No local Q3, Q2, IQ, Q4_K_S, Q5, Q6, or alternate Gemma GGUF variant is available. No model was downloaded or replaced during this investigation.

## Answers to the requested questions

1. **Where are CPU-mapped weights allocated?** `llama_mmap` maps the GGUF with read-only `MAP_SHARED`; the normal CPU backend buffer is created from a pointer into that mapping.
2. **Where is CPU_REPACK allocated?** `ggml_backend_cpu_repack_buffer_type_alloc_buffer` allocates normal CPU memory, then assigns CPU_REPACK callbacks and type metadata.
3. **Which tensors are repacked?** All 253 Q4_K tensors, totaling 2,165.625 MiB.
4. **Which formats trigger repack?** On this x86 build, Q4_0, Q4_K, IQ4_NL, and MXFP4 through AVX2, plus Q2_K through AVX512, subject to shape constraints. Only Q4_K occurs in this model's eligible set.
5. **Why does original mapped memory remain?** The same mapping backs non-repacked tensors, the used tensor range is retained as a contiguous mapping, and this commit does not discard interior source pages after repacking.
6. **Can the original remain file-backed?** It already is file-backed. The issue is that repacking faults those pages into RSS and no explicit post-repack discard occurs.
7. **Is CPU_REPACK duplicate data?** Yes, it is a second layout of the same Q4_K payload bytes, exactly 2,165.625 MiB.
8. **Is there a supported way to avoid duplicate residency while retaining optimized execution?** Yes, disable mmap or use supported direct I/O while keeping repack enabled. This should retain optimized CPU kernels without a persistent mapped source copy for repacked tensors.
9. **Is `use_extra_bufts=false` the only repack control?** It is the global disable, but per-tensor buffer overrides can selectively bypass repack, and non-mmap loading can avoid persistent source duplication without disabling repack.
10. **Are there other supported memory controls?** `use_mmap=false`, `use_direct_io=true` when supported, and per-tensor buffer overrides are relevant. `no_host`, KV precision, context, batch, and ubatch do not address the core duplicated weight representation.

## Recommended next experiment

Do not change production. Add one isolated controlled A/B configuration:

- Baseline: current production, mmap enabled, repack enabled.
- Candidate: mmap disabled, repack enabled.
- Optional follow-up: direct I/O enabled, repack enabled.

Freeze the same questions, retrieved chunks, prompts, sampling, context, batch, ubatch, threads, and seed. Measure model-load peak separately from steady inference peak because the non-mmap loader may retain a temporary buffer as large as 360 MiB during loading.

The candidate should be adopted only if it:

- remains at or below 7 GiB peak RSS, including model load;
- reproduces production answers or preserves measured accuracy;
- preserves the repacked prompt-processing advantage;
- does not introduce unacceptable model-load latency or storage I/O behavior.

No production change is recommended from source inspection alone.
