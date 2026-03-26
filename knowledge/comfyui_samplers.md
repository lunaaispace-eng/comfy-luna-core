---
id: comfyui_samplers
title: Samplers & Schedulers Reference
keywords: [sampler, scheduler, ksampler, euler, dpmpp, karras, sgm, steps, cfg, denoise, seed, noise, sampling]
category: core
priority: medium
---

## Sampler Names (ComfyUI)

### Standard Samplers
- `euler` — Fast, simple. Good default for most models.
- `euler_cfg_pp` — Euler with CFG++ (improved prompt adherence)
- `euler_ancestral` — Adds noise each step, more creative/varied. Good for Pony.
- `euler_ancestral_cfg_pp` — Ancestral with CFG++
- `heun` — 2nd order, better quality than euler at same steps, 2x slower
- `heunpp2` — Optimized Heun variant
- `lms` — Linear multi-step, fast but can overshoot
- `dpm_2` — 2nd order DPM solver
- `dpm_2_ancestral` — DPM-2 with ancestral noise
- `dpmpp_2s_ancestral` — DPM++ 2S ancestral, good variety
- `dpmpp_sde` — DPM++ SDE, good detail, slightly slower
- `dpmpp_sde_gpu` — GPU-optimized SDE variant
- `dpmpp_2m` — DPM++ 2M, excellent quality/speed balance. **Most recommended general sampler.**
- `dpmpp_2m_cfg_pp` — DPM++ 2M with CFG++
- `dpmpp_2m_sde` — DPM++ 2M SDE, best detail for most models. Slightly slower than 2m.
- `dpmpp_2m_sde_gpu` — GPU-optimized 2M SDE
- `dpmpp_3m_sde` — DPM++ 3M SDE, highest quality DPM++, slowest
- `dpmpp_3m_sde_gpu` — GPU-optimized 3M SDE
- `ddpm` — Denoising diffusion probabilistic model
- `ddim` — Denoising diffusion implicit model. Fast, deterministic.
- `uni_pc` — UniPC, fast convergence
- `uni_pc_bh2` — UniPC BH2 variant
- `ipndm` — Improved PNDM
- `ipndm_v` — IPNDM variant
- `deis` — Diffusion Exponential Integrator Sampler

### Special/Advanced Samplers
- `lcm` — Latent Consistency Model, 4-8 steps, needs LCM LoRA
- `res_momentumpc` — Restart sampler with momentum
- `trapezoidal` — Trapezoidal rule integration

## Scheduler Names

- `normal` — Linear noise schedule. Good default.
- `karras` — Karras noise schedule. **Recommended for most models.** Better detail.
- `exponential` — Exponential schedule. Good for high step counts.
- `sgm_uniform` — SGM uniform schedule. **Required for FLUX.**
- `simple` — Simple linear schedule. Alternative for FLUX.
- `ddim_uniform` — DDIM-specific uniform schedule
- `beta` — Beta distribution schedule
- `linear_quadratic` — Linear-quadratic hybrid
- `kl_optimal` — KL-optimal schedule

## Recommended Combinations by Model

### SD 1.5
| Sampler | Scheduler | Steps | CFG | Notes |
|---------|-----------|-------|-----|-------|
| `dpmpp_2m` | `karras` | 20-30 | 7-11 | Best general |
| `euler_ancestral` | `normal` | 20-30 | 7-9 | More variety |
| `dpmpp_sde` | `karras` | 20-25 | 7-9 | Best detail |
| `ddim` | `ddim_uniform` | 20-30 | 7 | Fast, consistent |

### SDXL
| Sampler | Scheduler | Steps | CFG | Notes |
|---------|-----------|-------|-----|-------|
| `dpmpp_2m` | `karras` | 20-35 | 5-8 | Best general |
| `euler` | `normal` | 25-35 | 6-8 | Simple, reliable |
| `dpmpp_2m_sde` | `karras` | 20-30 | 5-7 | Best detail |
| `dpmpp_sde` | `karras` | 20-25 | 6-8 | Good detail |

### Illustrious / NoobAI
| Sampler | Scheduler | Steps | CFG | Notes |
|---------|-----------|-------|-----|-------|
| `euler` | `normal` | 25-35 | 5-7 | Recommended |
| `dpmpp_2m` | `karras` | 25-35 | 5-7 | Alternative |
| `dpmpp_2m_sde` | `karras` | 25-30 | 5-7 | Best detail |

### Pony Diffusion V6
| Sampler | Scheduler | Steps | CFG | Notes |
|---------|-----------|-------|-----|-------|
| `euler_ancestral` | `normal` | 25-40 | 6-8 | Recommended |
| `dpmpp_2m_sde` | `karras` | 25-35 | 6-8 | Best detail |
| `dpmpp_sde` | `karras` | 25-30 | 7 | Good alternative |

### FLUX
| Sampler | Scheduler | Steps | CFG | Notes |
|---------|-----------|-------|-----|-------|
| `euler` | `simple` | 20-30 (Dev) | 1.0 | Standard |
| `euler` | `sgm_uniform` | 20-30 (Dev) | 1.0 | Alternative |
| `euler` | `simple` | 4-8 (Schnell) | 1.0 | Fast variant |

### WAN / Hunyuan Video
| Sampler | Scheduler | Steps | CFG | Notes |
|---------|-----------|-------|-----|-------|
| `euler` | `normal` | 20-30 | 3-6 | Recommended |
| `dpmpp_2m` | `karras` | 20-30 | 3-5 | Alternative |

## KSampler Parameter Reference

| Parameter | Type | Range | Default | Notes |
|-----------|------|-------|---------|-------|
| `seed` | INT | 0 to 2^64-1 | random | Controls noise pattern. Same seed = same result. |
| `steps` | INT | 1-10000 | 20 | More steps = more detail but slower. Diminishing returns past 30-40. |
| `cfg` | FLOAT | 0-100 | 8.0 | Classifier-free guidance. Higher = stronger prompt adherence but more artifacts. |
| `sampler_name` | COMBO | see list | euler | The denoising algorithm. |
| `scheduler` | COMBO | see list | normal | The noise schedule. |
| `denoise` | FLOAT | 0-1 | 1.0 | 1.0 = full generation, <1.0 = img2img/inpainting. Lower = less change. |

### control_after_generate (seed widget)
- `fixed` — same seed every time (reproducible)
- `increment` — seed +1 each generation
- `decrement` — seed -1 each generation
- `randomize` — new random seed each time (default behavior)

## Tuning Guide

**Blurry output:**
- Increase steps (25-35)
- Switch to `dpmpp_2m_sde` with `karras`
- Add hires fix (second KSampler at 0.4-0.6 denoise)
- Check resolution matches model (512 for SD1.5, 1024 for SDXL)

**Bad prompt adherence:**
- Increase CFG (try 7-9 for SD/SDXL, keep 1 for FLUX)
- Use more specific, shorter prompts
- Try `euler_cfg_pp` or `dpmpp_2m_cfg_pp` samplers
- Check CLIP skip setting (1 for SDXL, 2 for Illustrious/Pony)

**Artifacts / oversaturation:**
- Lower CFG (try 5-6)
- Reduce steps if using ancestral samplers
- Switch from ancestral to non-ancestral sampler
- Check model isn't corrupted

**Bad faces / hands:**
- Add FaceDetailer / HandDetailer (from Impact Pack)
- Use ADetailer node
- Add face/hand-specific negative prompts
- Use dedicated inpainting pass

**VRAM issues:**
- Enable tiled VAE decoding
- Lower resolution, use hires fix for upscaling
- Use fp8 model variants
- Reduce batch_size to 1
- Use `--lowvram` or `--novram` ComfyUI launch flags
