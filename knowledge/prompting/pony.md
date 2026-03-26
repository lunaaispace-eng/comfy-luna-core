---
id: prompting_pony
title: Pony Diffusion V6 Prompting Guide
keywords: [pony, ponyxl, pdxl, pony diffusion, score_9]
category: prompting
priority: low
base_models: ["Pony", "PDXL"]
---

## Pony Diffusion V6 XL Prompting Style

**Format:** Score tags + source tags + danbooru tags. Very specific tag system.

**Positive prompt structure:**
```
[score tags], [source tags], [character/subject tags], [style tags]
```

**Score tags (REQUIRED at start):**
```
score_9, score_8_up, score_7_up, score_6_up
```
More scores = higher quality threshold. Minimum: `score_9, score_8_up`

**Source tags (choose content type):**
```
source_anime        — anime/manga style
source_cartoon      — western cartoon style
source_furry        — furry art style
source_pony         — MLP style
source_realistic    — photorealistic
```

**Rating tags:**
```
rating_safe, rating_questionable, rating_explicit
```

**Tag examples (danbooru style):**
```
score_9, score_8_up, score_7_up, source_anime, 1girl, solo, long hair, school uniform, smile, looking at viewer, classroom, detailed background
```

**Negative prompt:**
```
score_1, score_2, score_3, source_pony, source_furry, ugly, deformed, bad anatomy, bad hands, worst quality, low quality, blurry
```

**Key settings:**
- Resolution: 1024x1024, 1152x896, 832x1216 (SDXL-based)
- CFG: 6-8
- Sampler: `euler_ancestral` or `dpmpp_2m_sde` with `karras`
- Steps: 25-40
- CLIP skip: 2

**Do NOT:**
- Forget score tags (quality drops significantly without them)
- Forget source tags (model defaults to mixed style)
- Use natural language
- Use SDXL quality tags like "masterpiece, best quality" (use score system instead)
