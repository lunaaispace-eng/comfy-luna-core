# Comfy-Luna-Core

**AI agent framework for ComfyUI that works from your real installation, not generic assumptions.**

Comfy-Luna-Core brings live AI assistance directly into ComfyUI. It inspects your installed nodes, models, workflows, custom node packs, model paths, and system capabilities in real time, then helps you create, modify, analyze, explain, and repair workflows through natural language.

![License](https://img.shields.io/badge/license-GPL--3.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![ComfyUI](https://img.shields.io/badge/ComfyUI-compatible-green.svg)
[![GitHub stars](https://img.shields.io/github/stars/lunaaispace-eng/comfy-luna-core?style=social)](https://github.com/lunaaispace-eng/comfy-luna-core/stargazers)

> Like this project? Give it a star and watch to stay updated!

---

## Demo

![Luna Core demo](demo.gif)

*Chat with AI to create and modify workflows instantly*

---

## Why Comfy-Luna-Core

Most AI workflow helpers rely on generic documentation, stale assumptions, or model memory.

Comfy-Luna-Core takes a different path.

It works from your **actual ComfyUI environment**:
- Installed nodes and custom node packs
- Available models with metadata (trigger words, base model, recommended settings)
- Saved workflows and official Comfy-Org templates
- Current canvas state
- System resources (GPU, VRAM, OS)
- Real runtime constraints

That means better suggestions, safer workflow edits, fewer hallucinations, and workflows built around what is actually available on your machine.

---

## Key Features

### 7 Interchangeable AI Backends

| Agent | Type | Vision | Tool Calling | Best For |
|-------|------|--------|-------------|----------|
| **Gemini** | API | Yes | Yes | Free tier, thinking models, forced tool use |
| **OpenAI** | API | Yes | Yes | GPT-4o quality |
| **Ollama** | Local | Yes | Yes | Free, private, offline |
| **Claude Code** | CLI | Yes | — | Best raw quality |
| **Kilo Code** | CLI | — | — | Open source alternative |
| **Aider** | CLI | — | — | Coding focus |
| **Open Interpreter** | CLI | — | — | Code execution |

**Tool Calling** = agent can search your nodes, inspect models with metadata, read/modify your workflow, test execution, and browse the web — all in real-time during the conversation.

### 16 Real-Time Tools

The agent doesn't guess — it **queries your actual ComfyUI installation** in real-time:

**Discovery Tools:**
| Tool | Description |
|------|-------------|
| `get_node_types(search, category)` | Search installed nodes by keyword or category |
| `get_node_info(class_type)` | Get full node specs — inputs, types, defaults, value ranges |
| `get_available_models(model_type, search, folder)` | List installed models with search/filter. Supports checkpoints, LoRAs, VAEs, upscale models, controlnets, CLIP, UNET, diffusion models, embeddings, ipadapter |
| `get_model_metadata(model_name)` | Get base model, trigger words, recommended settings, example prompts from CivitAI/LoRA Manager metadata |
| `get_current_workflow()` | Read the user's current workflow for analysis or modification |

**Workflow Reference Tools:**
| Tool | Description |
|------|-------------|
| `search_workflows(query, category, source)` | Search local and official workflows. Use `source='local'` for saved workflows, `source='official'` for Comfy-Org templates |
| `get_workflow_template(path)` | Load a specific workflow as reference for building or modifying |

**Canvas Manipulation Tools:**
| Tool | Description |
|------|-------------|
| `modify_node_input(node_id, input_name, value)` | Change settings on existing nodes with validation |
| `add_node(class_type, inputs, title, x, y)` | Add new nodes with optional canvas positioning |
| `remove_node(node_id)` | Remove nodes and clean up broken connections |
| `connect_nodes(source, output_slot, target, input_name)` | Wire nodes together with type compatibility checks |
| `auto_arrange_canvas()` | Auto-arrange all nodes for a clean layout |

**Execution Tools:**
| Tool | Description |
|------|-------------|
| `queue_prompt()` | Queue the current workflow for execution in ComfyUI |
| `get_execution_errors(limit)` | Check execution results — success/failure status, error messages, node IDs |

**Web Access Tools (require user approval):**
| Tool | Description |
|------|-------------|
| `web_search(query)` | Search the web for node docs, workflow guides, model info, troubleshooting |
| `web_fetch(url)` | Fetch and read a web page for detailed information |

> Every web request triggers an approval dialog — the agent cannot access the internet without your explicit permission.

### 31 Official Workflow Templates

Ships with official Comfy-Org workflow templates, auto-synced from GitHub:

| Category | Templates |
|----------|-----------|
| **Text-to-Image** | Standard, FLUX 2 Dev, Z-Image Turbo |
| **Text-to-Video** | Standard, WAN 2.2, LTX 2.0 |
| **Image-to-Video** | WAN 2.2, LTX 2.0, first/last frame |
| **Image Editing** | Standard, FLUX 2 Dev, FLUX 2 Klein, Qwen 2511 |
| **ControlNet** | Canny, depth, pose (Z-Image Turbo, LTX 2.0 variants) |
| **Image Processing** | Blur, sharpen, glow, film grain, color, levels, chromatic aberration, unsharp mask |

Templates work out of the box. Auto-sync on startup refreshes them when Comfy-Org publishes new ones.

### Workflow Registry
Indexes your entire local workflow library alongside official templates and makes everything searchable by keyword, category, node type, or source.

### Model Metadata Intelligence
Reads `.metadata.json` files from LoRA Manager and CivitAI to provide:
- **Trigger words** — automatically included in prompts
- **Base model** — architecture compatibility checking (SD 1.5, SDXL, Pony, Illustrious, FLUX)
- **Recommended settings** — weight, CFG, steps
- **Example prompts** — known-good prompts for the model

### Intent-Aware Planning
Understands the user request before acting:
- **build** — create a new workflow from scratch
- **modify** — change settings, nodes, or connections on an existing workflow
- **repair** — diagnose and fix broken workflows
- **inspect** — analyze and explain what a workflow does
- **prompt** — help write prompts for specific models
- **explain** — teach ComfyUI concepts and node behavior

### Direct Canvas Modification
Edits workflows directly on the current ComfyUI canvas instead of replacing the entire graph. No lost positions, groups, or layout.

### Execution Feedback Loop
The agent can queue workflows for execution and check the results:
1. Build or modify a workflow
2. Queue it with `queue_prompt()`
3. Check results with `get_execution_errors()`
4. Diagnose and fix issues automatically

### 7-Check Validation with Self-Correction
Every generated or modified workflow passes validation before applying:

1. **node_exists** — Is the node type installed?
2. **required_inputs** — Are all required inputs present?
3. **link_validity** — Do linked source nodes exist?
4. **output_slot_range** — Is the output slot index valid?
5. **type_compatibility** — Do connected types match (MODEL to MODEL, CLIP to CLIP)?
6. **value_ranges** — Are INT/FLOAT values within min/max bounds?
7. **combo_values** — Are dropdown values in the allowed options?

If errors are found, the agent automatically receives the report and retries (up to 3 rounds).

### Auto-Generated Knowledge
On first launch, Luna Core scans your ComfyUI installation and generates knowledge from:
- All installed nodes grouped by category with input/output specs
- All installed models (checkpoints, LoRAs, VAEs, upscale models, controlnets, CLIP, UNET, diffusion models, embeddings)
- Custom node packs
- Model paths (`extra_model_paths.yaml`)
- Global deduplication across categories with CLIP/checkpoint separation

This means the agent knows **your specific setup**, not generic defaults.

### Forced Tool Usage (Gemini)
Gemini agents use `ANY` mode on the first turn to guarantee at least one tool call before answering. Combined with minimal passive context, this prevents the agent from taking shortcuts or guessing from cached knowledge.

### Vision Support
Drag-drop, paste, or click to attach images for analysis — workflow screenshots, interface captures, and reference images (up to 5 images, 10MB each).

### System-Aware Behavior
Detects GPU, VRAM, operating system, and system constraints to adapt suggestions to the machine it is running on.

### VRAM-Conscious Runtime
Ollama models auto-unload from VRAM after responding (`keep_alive=0`), keeping VRAM free for ComfyUI.

### Multi-Model-Path Support
Reads `extra_model_paths.yaml` so models stored outside default ComfyUI directories are still discovered and usable.

### Model-Family Prompting Guides
Includes guidance tailored to different model families, helping the agent produce better prompts and workflow suggestions for the models you actually use.

### Integrated Chat UI
Docks in ComfyUI's sidebar or floats as a draggable/resizable window, keeping the assistant directly in your workflow environment.

---

## What It Can Do

### Build
```
You: Create a complex SDXL workflow with 2-pass sampling, LoRA, detailers, and upscaling

Agent: [Searches official templates for SDXL reference]
       [Searches 8+ node categories, finds your best upscaler]
       [Checks installed LoRAs with get_model_metadata for trigger words]
       [Builds workflow using ImageUpscaleWithModel instead of basic LatentUpscale]
       [Uses FaceDetailer if Impact Pack is installed]
       [Picks an actual checkpoint from your models folder]
       [Auto-arranges canvas layout]
       -> Apply Workflow
```

### Modify
```
You: Change the steps to 30 and CFG to 7.5 in my KSampler

Agent: [Reads workflow, finds KSampler node, validates value ranges]
       [Modifies settings directly on your canvas — no workflow replacement]
       Applied 2 modifications to your canvas
```

### Test
```
You: Run this workflow and tell me if there are errors

Agent: [Calls queue_prompt() to execute the workflow]
       [Calls get_execution_errors() to check results]
       "Execution failed on node 7 (KSampler) — invalid sampler name 'euler_a'.
        The valid options are 'euler_ancestral'. Let me fix that..."
       [Modifies the node and re-queues]
```

### Analyze
```
You: Analyze my current workflow and suggest improvements

Agent: [Reads your workflow via get_current_workflow()]
       [Calls get_model_metadata() on your checkpoint to check architecture]
       [Searches for better alternatives to your current nodes]
       "Your workflow uses basic LatentUpscale — you have RealESRGAN installed,
        switching to ImageUpscaleWithModel would give much better results..."
```

### Repair
```
You: Why is this workflow failing? Check missing models and broken connections.

Agent: [Validates workflow, identifies missing nodes and broken links]
       [Checks execution history for error details]
       [Suggests fixes and applies corrections]
```

### Search
```
You: Show me workflows related to WAN video generation

Agent: [Searches local workflows and official templates]
       [Returns matching workflows with node counts and categories]
```

### Vision
```
You: [uploads workflow screenshot] What's wrong with this workflow?

Agent: "I can see a type mismatch — VAEDecode is receiving MODEL instead of
        LATENT on the samples input. Here's the fix..."
```

---

## How It Works

1. Comfy-Luna-Core inspects your ComfyUI installation
2. It discovers installed nodes, models, workflows, and system details
3. It classifies your request by intent
4. It selects the right tools and context
5. It builds, edits, analyzes, or repairs the workflow
6. It validates the result before execution
7. It applies changes directly to the canvas
8. It can queue and test the workflow, then fix errors automatically

---

## Installation

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/lunaaispace-eng/comfy-luna-core.git
cd comfy-luna-core
pip install -r requirements.txt
```

Restart ComfyUI. Done!

### Setup an AI Agent

You need at least one agent configured:

<details>
<summary><b>Gemini (Recommended — Free Tier, Tool Calling, Vision)</b></summary>

Best for: Free tier, native tool calling, thinking models (2.5 Pro/Flash, 3.1 Pro).

```bash
# Set API key (either works)
export GEMINI_API_KEY=xxxxx
# or
export GOOGLE_API_KEY=xxxxx
```

Get key at: [aistudio.google.com/apikey](https://aistudio.google.com/apikey)

Install SDK:
```bash
pip install google-genai
```

> Supports streaming, vision, native function calling with forced tool use, and thinking models. The `customtools` variant is recommended for best tool compliance. Model list auto-fetched from the API.

</details>

<details>
<summary><b>Ollama (Free, Local, Private)</b></summary>

Best for: Local use, privacy, no API costs. Supports vision and tool calling.

1. **Install Ollama:** [ollama.com/download](https://ollama.com/download)

2. **Download a model:**
   ```bash
   ollama pull qwen2.5-coder:7b   # Recommended (4.7GB)
   ollama pull qwen2.5-coder:32b  # Best quality, needs 24GB+ VRAM (19GB)
   ollama pull llava:7b            # Vision model (4.7GB)
   ```

3. **Start Ollama:**
   ```bash
   ollama serve
   ```

> Models auto-unload from VRAM after responding (`keep_alive=0`), keeping VRAM free for ComfyUI.

</details>

<details>
<summary><b>OpenAI (GPT-4o, Tool Calling, Vision)</b></summary>

```bash
export OPENAI_API_KEY=sk-xxxxx
```

Get key at: [platform.openai.com/api-keys](https://platform.openai.com/api-keys)

> Supports streaming, vision, and native function calling.

</details>

<details>
<summary><b>Claude Code (CLI)</b></summary>

```bash
npm install -g @anthropic-ai/claude-code
claude  # Login with Claude Max or Pro account
```

Or use the included installer: double-click **`install_claude_cli.bat`** in the extension folder. It installs the CLI and creates a `CLAUDE.md` project context file in your ComfyUI root.

> Uses your existing Claude subscription. No separate API billing.

</details>

<details>
<summary><b>Codex (CLI — works with ChatGPT Plus)</b></summary>

```bash
npm install -g @openai/codex
codex  # Sign in with ChatGPT Plus/Pro account (no API key needed)
```

Or use the included installer: double-click **`install_codex_cli.bat`** in the extension folder. It installs the CLI and creates a project context file in your ComfyUI root.

> Works with ChatGPT Plus/Pro login — no API key required. Can also use `OPENAI_API_KEY` if preferred.

</details>

<details>
<summary><b>Other Agents (Kilo, Aider, Open Interpreter)</b></summary>

These CLI-based agents are supported but do not have tool calling or vision:

```bash
# Kilo Code
npm install -g kilo-code

# Aider
pip install aider-chat
export OPENAI_API_KEY=sk-xxxxx  # or ANTHROPIC_API_KEY

# Open Interpreter
pip install open-interpreter
```

</details>

### Use It

1. Open ComfyUI — look for the **Luna** icon in the left sidebar
2. Click to open the chat panel (or use it as a floating window)
3. Select your agent and model from the dropdowns
4. Start chatting! Attach images with drag-drop, paste, or the clip icon

---

## Configuration

Comfy-Luna-Core can work with:
- Default ComfyUI model paths
- `extra_model_paths.yaml`
- Local workflow libraries
- Official workflow template sources
- Multiple AI backend providers

Configuration can be extended for:
- Workflow source paths
- Backend selection
- API keys
- Ollama behavior
- System-specific preferences

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/luna/agents` | GET | List available agents with capabilities |
| `/luna/system` | GET | GPU, VRAM, OS info |
| `/luna/models` | GET | Available ComfyUI models |
| `/luna/custom-nodes` | GET | Installed custom nodes |
| `/luna/node-info` | GET | Full node registry from /object_info |
| `/luna/knowledge-categories` | GET | Available knowledge categories |
| `/luna/validate-workflow` | POST | Validate workflow JSON |
| `/luna/chat` | POST | Chat with streaming + tool calling |
| `/luna/apply-workflow` | POST | Apply workflow to ComfyUI canvas |
| `/luna/tool-approval` | POST | Approve/deny web access requests |

---

## Project Structure

```
comfy-luna-core/
├── __init__.py              # ComfyUI extension registration
├── controller.py            # HTTP API, agent coordination, tool loop, format conversion
├── agents/                  # AI backends
│   ├── base.py              # AgentBackend ABC, AgentMessage, system prompt (10 core rules)
│   ├── registry.py          # Agent auto-discovery
│   ├── tools.py             # Tool/function calling framework
│   ├── comfyui_tools.py     # 14 ComfyUI tools (discovery + manipulation + execution + search)
│   ├── web_tools.py         # Web search and fetch with user approval
│   ├── planner.py           # Intent classification and strategy routing
│   ├── ollama.py            # Ollama (local, vision, tools)
│   ├── gemini.py            # Gemini API (vision, tools, forced tool use, thinking models)
│   ├── codex.py             # OpenAI API (vision, tools)
│   ├── claude_code.py       # Claude Code CLI
│   ├── kilo.py              # Kilo Code CLI
│   ├── aider.py             # Aider CLI
│   └── open_interpreter.py  # Open Interpreter CLI
├── knowledge/               # Context-aware knowledge system
│   ├── manager.py           # Budget-based knowledge selection (per-agent budgets)
│   ├── auto_generator.py    # Auto-generates knowledge from ComfyUI (dedup, CLIP cleanup)
│   ├── quick_reference.md   # Core ComfyUI concepts
│   ├── auto/                # Auto-generated (installed_nodes.md, installed_models.md)
│   ├── prompting/           # Model-family prompting guides
│   └── user/                # User-provided custom knowledge
├── templates/               # Workflow registry
│   ├── registry.py          # Indexes and searches local + official workflows
│   ├── sync_official.py     # Downloads official Comfy-Org blueprints
│   └── official/            # 31 official templates (shipped + auto-synced)
├── system/                  # System monitoring
│   ├── monitor.py           # GPU/VRAM/model detection
│   └── model_metadata.py    # CivitAI/LoRA Manager metadata reader
├── providers/               # Unified service clients
│   └── comfyui_client.py    # Async HTTP client for ComfyUI endpoints
├── validation/              # Workflow validation
│   ├── node_registry.py     # Fetches node defs from /object_info
│   └── validator.py         # 7-check workflow validator
├── workflow/                # Workflow utilities
│   └── manipulator.py       # JSON workflow manipulation
├── nodes/                   # ComfyUI custom nodes
│   └── prompt_generator.py  # AgenticPromptGenerator node
├── web/                     # Frontend
│   └── panel.js             # Chat UI (sidebar + floating, canvas modification, tool approval)
└── tests/                   # Test suite
```

---

## Knowledge System

### Auto-Generated (from your installation)
On first launch, Luna Core generates knowledge from your actual ComfyUI setup:
- **`knowledge/auto/installed_nodes.md`** — All installed nodes grouped by category with input/output specs
- **`knowledge/auto/installed_models.md`** — All installed models with global deduplication, CLIP/checkpoint separation, GGUF/UNET split

These files are regenerated automatically and reflect your real installation.

### Model Metadata
Reads `.metadata.json` files created by LoRA Manager alongside model files. Provides trigger words, base model architecture, recommended settings, and example prompts — critical for the agent to suggest compatible models and write effective prompts.

### Prompting Guides
Model-family specific guides in `knowledge/prompting/` — tailored guidance for writing effective prompts for different model architectures.

### User Knowledge
Add your own `.md` files to `knowledge/user/` for custom context the agent should know about.

---

## Contributing

Contributions welcome!

1. Fork the repo
2. Create feature branch (`git checkout -b feature/amazing`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push (`git push origin feature/amazing`)
5. Open Pull Request

### Adding New Agent Backends

Create `agents/my_agent.py`:

```python
from .base import AgentBackend, AgentMessage, AgentConfig
from .registry import AgentRegistry

class MyAgentBackend(AgentBackend):
    @property
    def name(self) -> str:
        return "my_agent"

    @property
    def display_name(self) -> str:
        return "My Agent"

    @property
    def supported_models(self) -> list[str]:
        return ["model-1", "model-2"]

    @property
    def supports_tool_calling(self) -> bool:
        return True

    @property
    def supports_vision(self) -> bool:
        return True

    async def is_available(self) -> bool:
        return True

    async def query(self, messages, config):
        yield "Hello from my agent!"

    async def query_with_tools(self, messages, config, tools):
        # Implement tool-calling loop
        ...

AgentRegistry.register(MyAgentBackend)
```

---

## Design Goals
- Model-agnostic — works with any LLM backend
- Live-data-first — your installation is the source of truth
- Safe workflow modification — direct canvas edits, not full replacements
- Minimal hallucination — tools verify before the agent answers
- Execution feedback — build, test, fix in a loop
- Expandable architecture — add backends, tools, knowledge easily

---

## Roadmap
- CLI installers for Claude Code and Codex CLI
- Richer workflow registry with tagging and learning
- Blueprint and subgraph composition
- Stronger planner and multi-step routing
- Expanded validation and automatic repair
- More official template coverage as Comfy-Org publishes them
- Community template sharing

---

## Core Principle

Comfy-Luna-Core is built on one simple rule:

**Use the real ComfyUI installation as source of truth.**

- Live node definitions come first
- Real installed models with metadata come first
- Actual workflows and official templates come first
- System-aware reasoning comes first
- Generic model assumptions come last

---

## Philosophy

ComfyUI already contains rich structure, state, and information.

The goal is not to make an AI guess better.

The goal is to make it **see more clearly**.

---

## Troubleshooting

<details>
<summary><b>Panel not showing in sidebar</b></summary>

- Restart ComfyUI completely
- Check browser console for errors
- Older ComfyUI versions may not have the sidebar API — the panel falls back to floating mode

</details>

<details>
<summary><b>Agent shows "unavailable"</b></summary>

- **Ollama**: Is `ollama serve` running?
- **Gemini**: Is `GEMINI_API_KEY` or `GOOGLE_API_KEY` set? Is `google-genai` installed?
- **OpenAI**: Is `OPENAI_API_KEY` set?
- **Claude Code**: Is the CLI installed? (`claude --version`)

</details>

<details>
<summary><b>Workflow won't apply</b></summary>

- Check browser console for errors
- Some nodes may require custom node packs to be installed
- Check validation errors shown in chat

</details>

<details>
<summary><b>Tool calling not working</b></summary>

- Ensure you're using an agent that supports tools (Gemini, OpenAI, Ollama)
- CLI-based agents (Claude Code, Aider, Kilo) don't support tool calling
- Check that node registry loaded successfully (controller logs on startup)
- For Gemini: use the `customtools` model variant for best tool compliance

</details>

<details>
<summary><b>Models not showing or duplicated</b></summary>

- Ensure `extra_model_paths.yaml` is configured correctly
- Knowledge files are auto-regenerated on startup — restart ComfyUI
- CLIP category is automatically cleaned of checkpoint entries
- GGUF models are split into UNET category

</details>

<details>
<summary><b>LoRA trigger words missing</b></summary>

- Install LoRA Manager to generate `.metadata.json` files with CivitAI data
- The agent reads trigger words from these metadata files automatically
- Check that model paths match between ComfyUI and metadata files

</details>

<details>
<summary><b>Out of VRAM</b></summary>

- Use tiled VAE nodes (VAEEncodeTiled / VAEDecodeTiled)
- Reduce resolution
- Use fp8 models for FLUX
- Try SD1.5 instead of SDXL

</details>

---

## Disclaimer

**USE AT YOUR OWN RISK.** This software is provided "as is", without warranty of any kind.

- **API Costs**: The author is NOT responsible for any API costs or billing charges incurred while using this software
- **Third-Party Services**: You are responsible for complying with AI provider terms of service

---

## License

**GPL-3.0 License** — see [LICENSE](LICENSE)

- Free to use, modify, and distribute
- Commercial use allowed
- Derivative works must also be open source under GPL-3.0

---

## Credits

Developed by [lunaaispace](https://github.com/lunaaispace-eng)

Built with:
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI)
- [Google Gemini](https://aistudio.google.com)
- [Ollama](https://ollama.com)
- [OpenAI](https://openai.com)
