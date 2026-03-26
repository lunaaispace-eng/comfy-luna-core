---
id: comfyui_nodes_reference
title: ComfyUI Node System Reference
keywords: [node, widget, input, output, connection, type, MODEL, CLIP, VAE, CONDITIONING, LATENT, IMAGE, MASK, class_type, INPUT_TYPES, slot]
category: core
priority: medium
---

## Node Architecture

Every ComfyUI node is a Python class with:
- `INPUT_TYPES()` classmethod — defines required/optional inputs
- `RETURN_TYPES` — tuple of output type strings
- `RETURN_NAMES` — tuple of output slot names
- `FUNCTION` — name of the method to execute
- `CATEGORY` — where it appears in the node menu

### Input Types

**Widget inputs** (set by user in the node UI):
- `INT` — integer with min/max/step/default. Example: `("INT", {"default": 20, "min": 1, "max": 10000, "step": 1})`
- `FLOAT` — float with min/max/step/default. Example: `("FLOAT", {"default": 8.0, "min": 0.0, "max": 100.0, "step": 0.1})`
- `STRING` — text input. `{"multiline": True}` for prompt fields, `{"multiline": False}` for single line
- `BOOLEAN` — true/false toggle. `("BOOLEAN", {"default": True})`
- `COMBO` — dropdown list. Defined as a Python list: `(["option1", "option2", "option3"],)`

**Connection inputs** (linked from another node's output):
- `MODEL` — diffusion model weights
- `CLIP` — text encoder (CLIP-L, CLIP-G, T5XXL depending on architecture)
- `VAE` — variational autoencoder for latent↔image conversion
- `CONDITIONING` — encoded text prompt (positive or negative)
- `LATENT` — latent space tensor (what the model works on)
- `IMAGE` — pixel-space image tensor (0-1 float, BHWC format)
- `MASK` — single-channel mask tensor
- `NOISE` — noise pattern for sampling
- `SAMPLER` — sampler algorithm object
- `SIGMAS` — noise schedule for sampling
- `GUIDER` — guidance configuration object
- `CONTROL_NET` — loaded ControlNet model
- `STYLE_MODEL` — loaded style model (IP-Adapter, etc.)
- `CLIP_VISION` — CLIP vision encoder
- `UPSCALE_MODEL` — loaded upscale model (ESRGAN, etc.)
- `AUDIO` — audio tensor
- `MESH` — 3D mesh data

### Connection Rules
- Output type MUST match input type exactly (MODEL→MODEL, not MODEL→CLIP)
- One output can feed multiple inputs (fan-out)
- Each input accepts only ONE connection (no fan-in)
- Connections in API format: `["source_node_id", output_slot_index]`
- Output slots are 0-indexed based on RETURN_TYPES order

## Key Loader Nodes — Output Slot Mapping

**CheckpointLoaderSimple** (most common):
- Slot 0: MODEL
- Slot 1: CLIP
- Slot 2: VAE

**UNETLoader / DiffusionModelLoader**:
- Slot 0: MODEL

**DualCLIPLoader** (FLUX, SD3):
- Slot 0: CLIP (combined)

**CLIPLoader**:
- Slot 0: CLIP

**VAELoader**:
- Slot 0: VAE

**LoraLoader**:
- Input: MODEL, CLIP
- Slot 0: MODEL (with LoRA applied)
- Slot 1: CLIP (with LoRA applied)
- Widget: `lora_name` (COMBO), `strength_model` (FLOAT), `strength_clip` (FLOAT)

**ControlNetLoader**:
- Slot 0: CONTROL_NET

**UpscaleModelLoader**:
- Slot 0: UPSCALE_MODEL

## Core Processing Nodes

**CLIPTextEncode**:
- Input: CLIP (connection), text (STRING widget)
- Output: CONDITIONING (slot 0)

**KSampler** (standard sampler):
- Inputs: model (MODEL), positive (CONDITIONING), negative (CONDITIONING), latent_image (LATENT)
- Widgets: seed (INT), steps (INT), cfg (FLOAT), sampler_name (COMBO), scheduler (COMBO), denoise (FLOAT)
- Output: LATENT (slot 0)

**KSamplerAdvanced**:
- Same as KSampler plus: add_noise (enable/disable), start_at_step, end_at_step, return_with_leftover_noise
- Used for multi-pass generation and img2img control

**EmptyLatentImage**:
- Widgets: width (INT), height (INT), batch_size (INT)
- Output: LATENT (slot 0)

**VAEDecode**:
- Input: samples (LATENT), vae (VAE)
- Output: IMAGE (slot 0)

**VAEEncode**:
- Input: pixels (IMAGE), vae (VAE)
- Output: LATENT (slot 0)

**SaveImage**:
- Input: images (IMAGE)
- Widget: filename_prefix (STRING)

**ImageUpscaleWithModel**:
- Input: upscale_model (UPSCALE_MODEL), image (IMAGE)
- Output: IMAGE (slot 0)

## SDXL-Specific Nodes

**CLIPTextEncodeSDXL**:
- Separate `text_g` (CLIP-G, main prompt) and `text_l` (CLIP-L, detail/style)
- `width`, `height`, `target_width`, `target_height` for resolution conditioning
- Better results than basic CLIPTextEncode for SDXL models

## FLUX-Specific Nodes

FLUX uses a split architecture — model and text encoders loaded separately:
- **UNETLoader** → MODEL (FLUX model in fp8/gguf)
- **DualCLIPLoader** → CLIP (CLIP-L + T5XXL for FLUX)
- **CLIPTextEncode** → CONDITIONING (FLUX uses single positive, no negative)
- Some FLUX workflows use **FluxGuidance** node for guidance_scale instead of CFG

## ControlNet Application

**ControlNetApplyAdvanced**:
- Input: positive (CONDITIONING), negative (CONDITIONING), control_net (CONTROL_NET), image (IMAGE)
- Widgets: strength (FLOAT 0-1), start_percent (FLOAT 0-1), end_percent (FLOAT 0-1)
- Output: positive CONDITIONING (slot 0), negative CONDITIONING (slot 1)
- Insert between CLIPTextEncode and KSampler in the conditioning chain

## Node Modification Procedures

When modifying a node on canvas:
1. **Widget values** — Use `modify_node_input(node_id, input_name, value)` for INT, FLOAT, STRING, BOOLEAN, COMBO
2. **Connections** — Use `connect_nodes(source_id, output_slot, target_id, input_name)` to rewire
3. **Adding nodes** — Use `add_node(class_type, inputs, title)` then connect
4. **Removing nodes** — Use `remove_node(node_id)` — automatically cleans broken links

Always verify node exists with `get_node_info(class_type)` before using it. Widget names in the API may differ from display names.
