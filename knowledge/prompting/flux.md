---
id: prompting_flux
title: FLUX Prompting Guide
keywords: [flux, flux.1, flux dev, flux schnell, black forest]
category: prompting
priority: low
base_models: ["Flux.1 D", "Flux.1 S", "FLUX", "Flux"]
---

## FLUX Prompting Style

**Format:** Pure natural language. Long, descriptive sentences. NO tags, NO weights.

**Positive prompt structure:**
Write a detailed description as if describing the image to someone:
```
A portrait photograph of a young woman with auburn hair, standing in a sunlit garden. She wears a white linen dress and looks directly at the camera with a gentle smile. The background is softly blurred with warm golden hour lighting creating a bokeh effect. Shot on Canon EOS R5, 85mm f/1.4 lens. Professional studio quality.
```

**What makes FLUX different:**
- Understands natural language natively — no need for tags or weights
- Longer prompts = better results (2-4 sentences ideal)
- Can understand spatial relationships: "a cat sitting ON the left side of a red couch"
- Can render text in images: "a sign that reads 'Hello World'"
- Ignores negative prompts (don't bother with them)
- No (weight:1.3) syntax — just describe what matters more in detail

**Key settings:**
- Resolution: 1024x1024, 1360x768, 768x1360 (16:9), 1024x576, 576x1024
- CFG: 1.0 (FLUX uses guidance_scale differently, keep at 1)
- Sampler: `euler` with `simple` scheduler
- Steps: 20-30 for Dev, 4-8 for Schnell
- Use fp8 checkpoint to save VRAM
- Needs separate CLIP + T5XXL text encoders (not built into checkpoint)

**FLUX Schnell vs Dev:**
- Schnell: 4-8 steps, faster, slightly lower quality
- Dev: 20-30 steps, slower, higher quality

**Do NOT:**
- Use danbooru tags
- Use quality tags (masterpiece, best quality)
- Use weighted syntax (word:1.3)
- Use negative prompts (FLUX ignores them)
- Use CFG above 3 (causes artifacts)
- Forget to load T5XXL text encoder
