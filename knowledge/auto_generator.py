"""Auto-generate knowledge files from the actual ComfyUI installation.

Scans /object_info for installed nodes and discovers ALL model types
dynamically from loader nodes. Reads .metadata.json files for rich
model information (trigger words, base model, recommended settings).
Writes compact markdown files to knowledge/auto/.
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

import aiohttp

logger = logging.getLogger("luna_core.knowledge.auto")

AUTO_DIR = Path(__file__).parent / "auto"


async def generate_all(comfyui_url: str = "http://127.0.0.1:8188") -> List[Path]:
    """Generate all auto-knowledge files. Returns list of created files."""
    AUTO_DIR.mkdir(exist_ok=True)
    created = []

    nodes_path = await _generate_nodes_knowledge(comfyui_url)
    if nodes_path:
        created.append(nodes_path)

    models_path = await _generate_models_knowledge(comfyui_url)
    if models_path:
        created.append(models_path)

    return created


async def _generate_nodes_knowledge(comfyui_url: str) -> Optional[Path]:
    """Fetch /object_info and generate a compact node reference grouped by category."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{comfyui_url}/object_info", timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    logger.warning("Failed to fetch /object_info: %s", resp.status)
                    return None
                data = await resp.json()
    except Exception as e:
        logger.warning("Could not reach ComfyUI for node scan: %s", e)
        return None

    # Group nodes by category (compact — no input specs)
    categories: Dict[str, List[dict]] = {}
    for class_type, info in data.items():
        cat = info.get("category", "uncategorized")
        # Simplify deep categories: "loaders/video" -> "loaders"
        top_cat = cat.split("/")[0] if "/" in cat else cat
        if top_cat not in categories:
            categories[top_cat] = []

        node_summary = {"name": class_type}

        # Display name only if meaningfully different
        display = info.get("display_name", class_type)
        if display != class_type:
            node_summary["display"] = display

        # Output types only (inputs available via get_node_info tool)
        raw_outputs = info.get("output", [])
        if raw_outputs:
            flat_outputs = []
            for o in raw_outputs:
                if isinstance(o, list):
                    flat_outputs.extend(str(x) for x in o)
                else:
                    flat_outputs.append(str(o))
            node_summary["outputs"] = flat_outputs

        categories[top_cat].append(node_summary)

    sorted_cats = sorted(categories.keys())

    # Build compact markdown — discovery index only
    lines = [
        "---",
        "id: installed_nodes",
        "title: My Installed Nodes",
        "keywords: [nodes, custom nodes, installed, available]",
        "category: my_nodes",
        "priority: low",
        "---",
        "",
        f"**{len(data)} nodes installed** across {len(sorted_cats)} categories.",
        "Use get_node_info(class_type) for full input/output specs.",
        "",
    ]

    for cat in sorted_cats:
        nodes = sorted(categories[cat], key=lambda n: n["name"])
        lines.append(f"## {cat} ({len(nodes)} nodes)")
        lines.append("")

        for node in nodes:
            name = node["name"]
            display = node.get("display", "")
            outputs = node.get("outputs", [])
            out_str = " → " + ", ".join(outputs) if outputs else ""
            display_str = f" ({display})" if display else ""
            lines.append(f"- **{name}**{display_str}{out_str}")

        lines.append("")

    out_path = AUTO_DIR / "installed_nodes.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Generated node knowledge: %d nodes in %s", len(data), out_path)
    return out_path


# -----------------------------------------------------------------------
# Dynamic model discovery
# -----------------------------------------------------------------------

# Known loader nodes — ordered by priority so models land in the most
# specific category first.  CLIP/UNET loaders go last because they
# show checkpoint files that aren't really clip/unet-only models.
_KNOWN_LOADERS_ORDERED = [
    # Priority 1 — checkpoints
    ("CheckpointLoaderSimple", "ckpt_name", "checkpoints"),
    ("CheckpointLoader", "ckpt_name", "checkpoints"),
    ("unCLIPCheckpointLoader", "ckpt_name", "checkpoints"),
    # Priority 2 — loras
    ("LoraLoader", "lora_name", "loras"),
    ("LoraLoaderModelOnly", "lora_name", "loras"),
    # Priority 3 — vae
    ("VAELoader", "vae_name", "vae"),
    # Priority 4 — controlnet
    ("ControlNetLoader", "control_net_name", "controlnet"),
    # Priority 5 — upscale
    ("UpscaleModelLoader", "model_name", "upscale_models"),
    # Priority 6 — specialized
    ("StyleModelLoader", "style_model_name", "style_models"),
    ("GLIGENLoader", "gligen_name", "gligen"),
    ("HypernetworkLoader", "hypernetwork_name", "hypernetworks"),
    ("PhotoMakerLoader", "photomaker_model_name", "photomaker"),
    ("IPAdapterModelLoader", "ipadapter_file", "ipadapter"),
    ("InstantIDModelLoader", "instantid_file", "instantid"),
    # Priority 7 — unet/diffusion (after checkpoints to avoid dupes)
    ("UNETLoader", "unet_name", "unet"),
    ("DiffusionModelLoader", "unet_name", "diffusion_models"),
    # Priority 8 — clip (LAST — these list checkpoint files too)
    ("CLIPLoader", "clip_name", "clip"),
    ("DualCLIPLoader", "clip_name1", "clip"),
    ("CLIPVisionLoader", "clip_name", "clip_vision"),
]

# For backward compat with _guess_model_category
_KNOWN_LOADER_NAMES = {entry[0] for entry in _KNOWN_LOADERS_ORDERED}

# Junk model patterns to filter out
_JUNK_PATTERNS = {"tensorrt", "nvidia", "onnx_models", "nsfw_xl", "put_"}
_JUNK_NAMES = {"", "none", "[none]", "[no model]", "None"}


def _is_junk_model(name: str) -> bool:
    """Filter out system/junk model entries."""
    if not name or not isinstance(name, str):
        return True
    if name in _JUNK_NAMES:
        return True
    if len(name) < 3:
        return True
    name_lower = name.lower()
    return any(pat in name_lower for pat in _JUNK_PATTERNS)


async def discover_all_model_types(comfyui_url: str = "http://127.0.0.1:8188") -> Dict[str, List[str]]:
    """Dynamically discover ALL model types by scanning loader nodes.

    Uses priority-ordered loaders with cross-category deduplication
    so each model file appears in exactly one category (the most specific).

    Returns:
        Dict mapping model_type -> list of model filenames
    """
    all_models: Dict[str, List[str]] = {}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{comfyui_url}/object_info",
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    return all_models
                all_nodes = await resp.json()

    except Exception as e:
        logger.warning("Could not fetch object_info for model discovery: %s", e)
        return all_models

    # Global dedup set — each model filename appears in exactly one category
    global_seen: Set[str] = set()

    def _add_models(options: list, model_type: str):
        """Add models to category, skipping globally seen and junk."""
        existing = all_models.get(model_type, [])
        existing_set = set(existing)
        for name in options:
            if not isinstance(name, str):
                continue
            if name in global_seen or name in existing_set:
                continue
            if _is_junk_model(name):
                continue
            existing.append(name)
            existing_set.add(name)
            global_seen.add(name)
        if existing:
            all_models[model_type] = existing

    # 1. Process known loaders in priority order
    for node_class, input_name, model_type in _KNOWN_LOADERS_ORDERED:
        node_info = all_nodes.get(node_class)
        if not node_info:
            continue

        required = node_info.get("input", {}).get("required", {})
        optional = node_info.get("input", {}).get("optional", {})

        for inputs in [required, optional]:
            inp_def = inputs.get(input_name)
            if inp_def and isinstance(inp_def, list) and len(inp_def) > 0:
                options = inp_def[0]
                if isinstance(options, list):
                    _add_models(options, model_type)

    # 2. Auto-discover unknown loaders
    for node_class, node_info in all_nodes.items():
        if node_class in _KNOWN_LOADER_NAMES:
            continue
        name_lower = node_class.lower()
        if "load" not in name_lower:
            continue

        required = node_info.get("input", {}).get("required", {})
        for inp_name, inp_def in required.items():
            if not isinstance(inp_def, list) or len(inp_def) == 0:
                continue
            options = inp_def[0]
            if not isinstance(options, list) or len(options) == 0:
                continue

            sample = options[0] if options else ""
            if isinstance(sample, str) and any(
                sample.endswith(ext) for ext in (".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".onnx")
            ):
                category = _guess_model_category(inp_name, node_class)
                _add_models(options, category)
                logger.debug(
                    "Auto-discovered model type '%s' from %s.%s (%d models)",
                    category, node_class, inp_name, len(options),
                )

    return all_models


def _guess_model_category(input_name: str, node_class: str) -> str:
    """Guess model category from input name and node class."""
    name = (input_name + " " + node_class).lower()
    if "lora" in name:
        return "loras"
    if "checkpoint" in name or "ckpt" in name:
        return "checkpoints"
    if "vae" in name:
        return "vae"
    if "controlnet" in name or "control_net" in name:
        return "controlnet"
    if "upscale" in name:
        return "upscale_models"
    if "clip_vision" in name or "clipvision" in name:
        return "clip_vision"
    if "clip" in name:
        return "clip"
    if "unet" in name or "diffusion" in name:
        return "diffusion_models"
    if "embed" in name:
        return "embeddings"
    if "ipadapter" in name or "ip_adapter" in name:
        return "ipadapter"
    if "instantid" in name:
        return "instantid"
    if "style" in name:
        return "style_models"
    if "gligen" in name:
        return "gligen"
    if "hypernet" in name:
        return "hypernetworks"
    if "photomaker" in name:
        return "photomaker"
    # Fallback: use input name
    return input_name.replace("_name", "").replace("_file", "")


async def _generate_models_knowledge(comfyui_url: str) -> Optional[Path]:
    """Discover ALL model types dynamically and generate a model reference.

    Uses dynamic loader discovery to find every model type, including
    those from extra_model_paths.yaml. Also reads .metadata.json files
    for rich model information.
    """
    # Dynamic discovery of all model types
    all_models = await discover_all_model_types(comfyui_url)

    if not any(all_models.values()):
        return None

    # Try to load metadata for models that have .metadata.json files
    from ..system.model_metadata import scan_metadata_files, get_model_metadata

    # Find ComfyUI model directories to scan for metadata
    model_dirs = _find_model_directories()
    if model_dirs:
        scan_metadata_files(model_dirs)

    # Build markdown
    total = sum(len(v) for v in all_models.values())
    lines = [
        "---",
        "id: installed_models",
        "title: My Installed Models",
        "keywords: [models, checkpoint, lora, vae, controlnet, upscale, clip, unet, diffusion, installed]",
        "category: my_models",
        "priority: low",
        "---",
        "",
        f"**{total} models installed** across {len(all_models)} categories.",
        f"Auto-generated from ComfyUI loader nodes (includes extra_model_paths).",
        "",
    ]

    for model_type in sorted(all_models.keys()):
        names = all_models[model_type]
        if not names:
            continue
        lines.append(f"## {model_type.replace('_', ' ').title()} ({len(names)})")
        lines.append("")

        for name in sorted(names):
            meta = get_model_metadata(name)
            if meta:
                base = meta.get("base_model", "")
                trigger = meta.get("trigger_words", [])
                model_name = meta.get("model_name", "")

                details = []
                if model_name and model_name != name:
                    details.append(model_name)
                if base:
                    details.append(f"base: {base}")
                if trigger:
                    details.append(f"triggers: {', '.join(trigger[:5])}")

                if details:
                    lines.append(f"- {name} — {' | '.join(details)}")
                else:
                    lines.append(f"- {name}")
            else:
                lines.append(f"- {name}")

        lines.append("")

    out_path = AUTO_DIR / "installed_models.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Generated model knowledge: %d models across %d types in %s",
                total, len(all_models), out_path)
    return out_path


def _find_model_directories() -> List[str]:
    """Find ComfyUI model directories to scan for .metadata.json files.

    Uses the extension's own path to locate ComfyUI root reliably
    (custom_nodes/comfy-luna-core/knowledge/ -> ComfyUI root is 3 levels up).
    Also checks extra_model_paths.yaml for external model directories.
    """
    dirs = []
    seen = set()

    def _add_dir(d: Path):
        s = str(d)
        if s not in seen and d.exists():
            dirs.append(s)
            seen.add(s)

    # Extension is at: ComfyUI/custom_nodes/comfy-luna-core/knowledge/auto_generator.py
    # ComfyUI root is 3 levels up from this file's directory
    extension_root = Path(__file__).parent.parent  # comfy-luna-core/
    comfyui_root = extension_root.parent.parent     # ComfyUI/

    # Also try cwd as fallback (for development/testing)
    candidates = [comfyui_root, Path.cwd(), Path.cwd().parent]

    for candidate in candidates:
        models_dir = candidate / "models"
        if not models_dir.exists():
            continue

        _add_dir(models_dir)
        # Add each model subfolder for metadata scanning
        for sub in models_dir.iterdir():
            if sub.is_dir():
                _add_dir(sub)

        # Check for extra_model_paths.yaml
        extra_yaml = candidate / "extra_model_paths.yaml"
        if extra_yaml.exists():
            try:
                import yaml
                config = yaml.safe_load(extra_yaml.read_text(encoding="utf-8"))
                if isinstance(config, dict):
                    for section_name, section in config.items():
                        if not isinstance(section, dict):
                            continue
                        base_path = section.get("base_path", "")
                        for key, subpath in section.items():
                            if key in ("base_path", "is_default"):
                                continue
                            if isinstance(subpath, str):
                                full_path = Path(base_path) / subpath if base_path else Path(subpath)
                                if full_path.exists():
                                    _add_dir(full_path)
            except Exception as e:
                logger.debug("Could not parse extra_model_paths.yaml: %s", e)

        break  # Found ComfyUI root

    if dirs:
        logger.info("Found %d model directories to scan for metadata", len(dirs))
    else:
        logger.warning("No model directories found. ComfyUI root: %s", comfyui_root)

    return dirs
