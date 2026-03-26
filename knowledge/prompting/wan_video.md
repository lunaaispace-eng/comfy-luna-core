---
id: prompting_wan
title: WAN Video Prompting Guide
keywords: [wan, wan2, hunyuan, video, animate, motion, temporal]
category: prompting
priority: low
base_models: ["WAN", "Hunyuan Video"]
---

## WAN / Hunyuan Video Prompting Style

**Format:** Natural language with motion/temporal descriptions.

**Positive prompt structure:**
```
[scene description], [subject action/motion], [camera movement], [style], [quality]
```

**Example:**
```
A woman walking through a sunlit forest path, autumn leaves falling gently around her, camera slowly tracking forward, cinematic, natural lighting, 4k quality, smooth motion
```

**Motion keywords:**
- `walking, running, turning, dancing, waving, nodding`
- `camera pan left, camera tracking, slow zoom in, static shot`
- `smooth motion, fluid movement, slow motion`
- `leaves falling, hair blowing in wind, water flowing`

**Quality tags for video:**
```
high quality, smooth motion, consistent, stable, cinematic, 4k
```

**Negative prompt:**
```
blurry, flickering, jittery, low quality, distorted, deformed, static, no motion, watermark, text
```

**Key settings:**
- Resolution: 512x512 or 768x512 for WAN (lower = more stable)
- Steps: 20-30
- CFG: 3-6 (lower is better for video consistency)
- Frames: 16-48 typical
- Context overlap: higher = less flickering (8-16)

**Do NOT:**
- Use very high CFG (causes flickering between frames)
- Request too many frames without enough VRAM
- Use tag-based prompting (use natural language)
- Forget to describe motion/action (or video will be static)
