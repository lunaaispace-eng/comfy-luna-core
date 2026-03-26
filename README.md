# Comfy-Luna-Core

**AI agent framework for ComfyUI that works from your real installation, not generic assumptions.**

Comfy-Luna-Core brings live AI assistance directly into ComfyUI. It inspects your installed nodes, models, workflows, custom node packs, model paths, and system capabilities in real time, then helps you create, modify, analyze, explain, and repair workflows through natural language.

---

## Why Comfy-Luna-Core

Most AI workflow helpers rely on generic documentation, stale assumptions, or model memory.

Comfy-Luna-Core takes a different path.

It works from your **actual ComfyUI environment**:
- installed nodes
- available models
- saved workflows
- current canvas state
- system resources
- real runtime constraints

That means better suggestions, safer workflow edits, fewer hallucinations, and workflows built around what is actually available on your machine.

---

## Key Features

### 7 interchangeable AI backends
Use the same framework with:
- Gemini
- OpenAI
- Ollama
- Claude Code
- Kilo
- Aider
- Open Interpreter

### 11 real-time ComfyUI tools
Query your live environment directly:
- installed nodes
- model availability
- saved workflows
- canvas state
- workflow structure
- validation context

### Workflow Registry
Indexes your workflow library and makes it searchable, so the agent can find relevant references, patterns, and starting points from your own environment.

### Official template and blueprint sync
Pulls official Comfy workflow templates and blueprints, giving the system clean baseline references for workflow creation and extension.

### Intent-aware planning
Understands the user request before acting, including:
- build
- modify
- repair
- inspect
- prompt
- explain

### Direct canvas modification
Edits workflows directly on the current ComfyUI canvas instead of replacing the entire graph.

### 7-check validation with self-correction
Runs validation before execution and can attempt automatic repair for up to 3 rounds when issues are detected.

### Auto-generated knowledge
Scans your ComfyUI installation and builds knowledge from:
- installed nodes
- models
- custom node packs
- workflow sources
- model paths

### Vision support
Can analyze workflow screenshots, interface captures, and reference images to help interpret graphs, troubleshoot issues, and guide workflow creation.

### System-aware behavior
Detects GPU, VRAM, operating system, and system constraints to adapt suggestions to the machine it is running on.

### VRAM-conscious runtime
Supports Ollama auto-unload after response to reduce memory pressure on local setups.

### Multi-model-path support
Reads `extra_model_paths.yaml` so models stored outside default ComfyUI directories are still discovered and usable.

### Model-family prompting guides
Includes guidance tailored to different model families, helping the agent produce better prompts and workflow suggestions for the models you actually use.

### Integrated chat UI
Runs inside ComfyUI as a sidebar or floating panel, keeping the assistant directly in your workflow environment.

---

## What It Enables

With Comfy-Luna-Core, you can:
- create workflows from natural language
- inspect and explain existing graphs
- modify nodes and connections in place
- search your workflow library for known patterns
- repair broken workflows before running them
- adapt suggestions to your installed models and nodes
- work with multiple AI backends through one unified interface

---

## Core Principle

Comfy-Luna-Core is built on one simple rule:

**Use the real ComfyUI installation as source of truth.**

That means:
- live node definitions come first
- real installed models come first
- actual workflows come first
- system-aware reasoning comes first
- generic model assumptions come last

---

## How It Works

1. Comfy-Luna-Core inspects your ComfyUI installation
2. It discovers installed nodes, models, workflows, and system details
3. It classifies your request by intent
4. It selects the right tools and context
5. It builds, edits, analyzes, or repairs the workflow
6. It validates the result before execution
7. It applies changes directly to the canvas when possible

---

## Typical Use Cases

### Build
Create a basic SDXL txt2img workflow.

### Modify
Replace the sampler in my current workflow and add a highres fix branch.

### Repair
Why is this workflow failing? Check missing models and broken connections.

### Inspect
Explain what this workflow does and which section controls upscaling.

### Search
Show me workflows related to WAN video generation.

### Prompt
Write a strong prompt for this model and workflow type.

---

## Installation

Clone into your ComfyUI custom nodes folder:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/lunaaispace-eng/comfy-luna-core
```

Install dependencies:

```bash
cd comfy-luna-core
pip install -r requirements.txt
```

Restart ComfyUI.

---

## Configuration

Comfy-Luna-Core can work with:
- default ComfyUI model paths
- `extra_model_paths.yaml`
- local workflow libraries
- official workflow template sources
- multiple AI backend providers

Configuration can be extended for:
- workflow source paths
- backend selection
- API keys
- Ollama behavior
- system-specific preferences

---

## Design Goals
- model-agnostic
- live-data-first
- safe workflow modification
- minimal hallucination
- expandable architecture
- practical use inside real ComfyUI environments

---

## Roadmap
- richer workflow registry and search
- deeper official template integration
- better blueprint and subgraph composition
- stronger planner and routing logic
- improved local workflow pattern learning
- expanded validation and repair
- continued backend refinement

---

## Philosophy

ComfyUI already contains rich structure, state, and information.

The goal is not to make an AI guess better.

The goal is to make it see more clearly.

---

## License

**GPL-3.0 License** — see [LICENSE](LICENSE)

---

Developed by [lunaaispace](https://github.com/lunaaispace-eng)
