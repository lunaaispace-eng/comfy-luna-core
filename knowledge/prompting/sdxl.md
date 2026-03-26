---
id: prompting_sdxl
title: SDXL Prompting Guide
keywords: [sdxl, xl, juggernaut, realvis, dreamshaper, colossus, copax]
category: prompting
priority: low
base_models: ["SDXL 1.0", "SDXL"]
---

## SDXL Prompting Style

**Format:** Natural language descriptions + quality tags. Weighted emphasis with (word:weight).

**Positive prompt structure:**
```
[subject description], [scene/environment], [lighting], [style], [quality tags]
```

**Quality tags (add at end):**
- `masterpiece, best quality, high resolution, 8k, detailed`
- For photos: `photorealistic, RAW photo, DSLR, sharp focus, bokeh`
- For art: `digital art, trending on artstation, highly detailed`

**Negative prompt (important for SDXL):**
```
worst quality, low quality, normal quality, blurry, deformed, ugly, disfigured, bad anatomy, bad hands, extra fingers, missing fingers, watermark, text, signature
```

**Weight syntax:** `(word:1.3)` increases emphasis, `(word:0.7)` decreases. Range: 0.5-1.5 typical.

**Key settings:**
- Resolution: 1024x1024, 1152x896, 896x1152, 1216x832, 832x1216
- CFG: 5-8 (lower = more creative, higher = more prompt-following)
- Sampler: `dpmpp_2m` or `euler` with `karras` scheduler
- Steps: 20-35
- Use CLIPTextEncodeSDXL with separate text_g and text_l for best results
- text_g = main prompt, text_l = details/style

**Do NOT:**
- Use danbooru/booru tags (those are for Illustrious/Pony)
- Use score tags (score_9, etc.)
- Go above CFG 12 (causes artifacts)
