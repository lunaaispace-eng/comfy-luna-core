---
id: quick_reference
title: ComfyUI Quick Reference
keywords: [comfyui, workflow, nodes, basics, help, build, create, modify, change, settings]
category: core
priority: high
---

## Standard Workflow Pipeline

```
Checkpoint → CLIP → TextEncode (pos/neg) → KSampler → VAEDecode → SaveImage
                                              ↑
                                     EmptyLatentImage
```

### Essential Node Chain
1. **CheckpointLoaderSimple** → MODEL(0), CLIP(1), VAE(2)
2. **CLIPTextEncode** × 2 → positive CONDITIONING, negative CONDITIONING
3. **EmptyLatentImage** → LATENT (set resolution here)
4. **KSampler** → takes all above → outputs LATENT
5. **VAEDecode** → LATENT + VAE → IMAGE
6. **SaveImage** → IMAGE → file

### Adding LoRA
Insert **LoraLoader** between checkpoint and everything downstream:
- Input: MODEL + CLIP from checkpoint
- Output: modified MODEL + CLIP (feed these to KSampler and CLIPTextEncode)
- Set `strength_model` and `strength_clip` (0.5-1.0 typical)

### Adding ControlNet
Insert **ControlNetApplyAdvanced** in the conditioning chain:
- Input: positive + negative CONDITIONING, loaded CONTROL_NET, preprocessed IMAGE
- Output: modified positive + negative CONDITIONING (feed to KSampler)
- Set `strength` (0.3-1.0), `start_percent`, `end_percent`

## Resolution by Model Family

| Model | Resolutions | Notes |
|-------|------------|-------|
| SD 1.5 | 512×512, 512×768, 768×512 | Never above 768 without hires fix |
| SDXL | 1024×1024, 1152×896, 896×1152, 1216×832, 832×1216 | |
| Illustrious/NoobAI | Same as SDXL | SDXL architecture |
| Pony V6 | Same as SDXL | SDXL architecture |
| FLUX | 1024×1024, 1360×768, 768×1360 | |
| WAN Video | 512×512, 768×512 | Lower = more stable |

## How To: Step-by-Step Procedures

### Build a txt2img workflow from scratch
1. `get_available_models("checkpoints")` — pick a checkpoint
2. `get_model_metadata(checkpoint_name)` — learn base model, triggers, settings
3. `get_node_info("CheckpointLoaderSimple")` — verify inputs
4. Add nodes in order: Checkpoint → CLIPTextEncode (×2) → EmptyLatentImage → KSampler → VAEDecode → SaveImage
5. Connect them following the pipeline above
6. Set resolution based on model family
7. Set sampler/scheduler/steps/cfg based on model family
8. Write prompts matching the model's prompting style

### Modify an existing workflow
1. `get_current_workflow()` — see what's on canvas NOW
2. Identify the node to change by ID
3. For widget changes: `modify_node_input(node_id, input_name, value)`
4. For rewiring: `connect_nodes(source_id, output_slot, target_id, input_name)`
5. For adding nodes: `add_node(class_type, inputs, title)` then connect

### Switch to a different model
1. `get_current_workflow()` — read current state
2. `get_available_models("checkpoints")` — find the new model
3. `get_model_metadata(new_model)` — check base model type
4. `modify_node_input(checkpoint_node_id, "ckpt_name", new_model_name)`
5. If switching model FAMILY (e.g., SD1.5→SDXL): also update resolution, CFG, sampler, prompts

### Add a LoRA to existing workflow
1. `get_current_workflow()` — find checkpoint node ID
2. `get_available_models("loras")` — pick a LoRA
3. `get_model_metadata(lora_name)` — get trigger words
4. Add LoraLoader node, connect MODEL+CLIP from checkpoint
5. Reconnect downstream nodes to use LoraLoader's outputs instead
6. Add trigger words to the positive prompt

## Connection Rules
- Output types must match input types exactly (MODEL→MODEL, not MODEL→CLIP)
- One output can connect to multiple inputs (fan-out OK)
- Each input accepts only one connection (no fan-in)
- Connections in API format: `["source_node_id", output_slot_index]`

## Quick Settings by Model Family

| Model | CFG | Sampler | Scheduler | Steps | CLIP Skip |
|-------|-----|---------|-----------|-------|-----------|
| SD 1.5 | 7-11 | dpmpp_2m | karras | 20-30 | 1 |
| SDXL | 5-8 | dpmpp_2m | karras | 20-35 | 1 |
| Illustrious | 5-7 | euler | normal | 25-35 | 2 |
| Pony V6 | 6-8 | euler_ancestral | normal | 25-40 | 2 |
| FLUX | 1.0 | euler | simple | 20-30 (Dev), 4-8 (Schnell) | N/A |
| WAN Video | 3-6 | euler | normal | 20-30 | 1 |
