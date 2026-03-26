---
id: prompting_illustrious
title: Illustrious/NoobAI Prompting Guide
keywords: [illustrious, noob, noobai, wai, dasiwal, animagine]
category: prompting
priority: low
base_models: ["Illustrious", "NoobAI", "Noob"]
---

## Illustrious / NoobAI Prompting Style

**Format:** Danbooru tag-based. Comma-separated tags, NOT natural language sentences.

**Positive prompt structure:**
```
[quality scores], [character tags], [clothing/appearance], [pose/action], [background/scene], [style tags]
```

**Quality scores (REQUIRED at start):**
```
masterpiece, best quality, absurdres, highres
```
Some Illustrious finetunes also support:
```
score_9, score_8_up, score_7_up
```

**Tag examples:**
- Characters: `1girl, solo, long hair, blonde hair, blue eyes, large breasts`
- Clothing: `school uniform, white shirt, pleated skirt, thighhighs`
- Pose: `standing, looking at viewer, smile, arms behind back`
- Scene: `outdoors, sky, clouds, city, sunset`
- Style: `anime coloring, flat color, cel shading, watercolor`

**Negative prompt:**
```
worst quality, low quality, normal quality, lowres, bad anatomy, bad hands, extra digits, fewer digits, cropped, watermark, username, text
```

**Key settings:**
- Resolution: 1024x1024, 1152x896, 896x1152, 832x1216 (SDXL-based)
- CFG: 5-7
- Sampler: `euler` or `dpmpp_2m` with `normal` or `karras` scheduler
- Steps: 25-35
- CLIP skip: 2 (important!)

**Do NOT:**
- Write natural language sentences
- Use FLUX-style descriptive paragraphs
- Forget quality scores at the start
- Use CFG above 10
