---
id: comfyui_api_format
title: ComfyUI Workflow Format Reference
keywords: [api, format, json, workflow, node, link, connection, class_type, inputs, output, prompt, queue]
category: core
priority: medium
---

## API Format (what tools use)

The API format is a flat dict with string node IDs. This is what `/prompt` accepts and what `get_current_workflow()` returns.

```json
{
  "1": {
    "class_type": "CheckpointLoaderSimple",
    "inputs": {
      "ckpt_name": "dreamshaper_8.safetensors"
    },
    "_meta": {"title": "Load Checkpoint"}
  },
  "2": {
    "class_type": "CLIPTextEncode",
    "inputs": {
      "text": "a beautiful landscape",
      "clip": ["1", 1]
    },
    "_meta": {"title": "Positive Prompt"}
  },
  "3": {
    "class_type": "KSampler",
    "inputs": {
      "model": ["1", 0],
      "positive": ["2", 0],
      "negative": ["4", 0],
      "latent_image": ["5", 0],
      "seed": 42,
      "steps": 20,
      "cfg": 7.0,
      "sampler_name": "dpmpp_2m",
      "scheduler": "karras",
      "denoise": 1.0
    }
  }
}
```

### Key rules:
- **Node IDs are strings**: `"1"`, `"2"`, `"15"` — even though they look like numbers
- **Connections**: `["source_node_id", output_slot_index]` — source ID is a string, slot is an int
- **Widget values**: set directly as values in `inputs` — `"steps": 20`, `"cfg": 7.0`
- **`_meta`**: optional, only contains `title` for display name
- **Missing `_meta`**: node will show its class_type as title

### How to read connections:
`"model": ["1", 0]` means: this node's `model` input is connected to node "1", output slot 0.

For CheckpointLoaderSimple:
- `["1", 0]` = MODEL output
- `["1", 1]` = CLIP output
- `["1", 2]` = VAE output

## UI Format (LiteGraph internal)

The UI format is what LiteGraph uses internally. It has separate `nodes` and `links` arrays. You do NOT need to produce this — the tools work with API format.

```json
{
  "nodes": [
    {
      "id": 1,
      "type": "CheckpointLoaderSimple",
      "pos": [100, 200],
      "size": [315, 98],
      "widgets_values": ["dreamshaper_8.safetensors"],
      "outputs": [
        {"name": "MODEL", "type": "MODEL", "links": [1]},
        {"name": "CLIP", "type": "CLIP", "links": [2, 3]},
        {"name": "VAE", "type": "VAE", "links": [4]}
      ]
    }
  ],
  "links": [
    [1, 1, 0, 3, 0, "MODEL"],
    [2, 1, 1, 2, 0, "CLIP"]
  ]
}
```

Link format: `[link_id, source_node_id, source_slot, target_node_id, target_slot, type]`

## Converting Between Formats

The agent tools handle this automatically:
- `get_current_workflow()` returns API format (converted from canvas UI format)
- `add_node()`, `modify_node_input()`, `connect_nodes()` work in API format
- The frontend converts modifications back to LiteGraph operations

## Queuing a Prompt

POST to `/prompt` with:
```json
{
  "prompt": { /* API format workflow */ },
  "client_id": "unique-session-id"
}
```

## Common API Endpoints

- `GET /object_info` — all registered node definitions (class_type → inputs/outputs)
- `GET /object_info/{class_type}` — single node definition
- `POST /prompt` — queue a workflow for execution
- `GET /history` — execution history
- `GET /queue` — current queue status
- `POST /interrupt` — stop current execution
- `GET /system_stats` — VRAM usage, device info
- `GET /extensions` — list of loaded extensions
- `GET /embeddings` — list of available textual inversions

## Workflow Validation

Before submitting a workflow:
1. Every `class_type` must exist in `/object_info`
2. All required inputs must be present (check `input.required`)
3. Connection types must match (MODEL→MODEL, not MODEL→CLIP)
4. COMBO values must be from the allowed list (check with `get_node_info`)
5. INT/FLOAT values must be within min/max range
6. No circular connections allowed
