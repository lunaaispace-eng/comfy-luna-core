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

    # Group nodes by category
    categories: Dict[str, List[dict]] = {}
    for class_type, info in data.items():
        cat = info.get("category", "uncategorized")
        # Simplify deep categories: "loaders/video" -> "loaders"
        top_cat = cat.split("/")[0] if "/" in cat else cat
        if top_cat not in categories:
            categories[top_cat] = []

        # Extract compact node summary
        node_summary = {"name": class_type}

        # Display name if different
        display = info.get("display_name", class_type)
        if display != class_type:
            node_summary["display"] = display

        # Inputs (required only, compact)
        required = info.get("input", {}).get("required", {})
        if required:
            inputs = {}
            for inp_name, inp_def in required.items():
                if isinstance(inp_def, list) and len(inp_def) > 0:
                    inp_type = inp_def[0]
                    if isinstance(inp_type, list):
                        # COMBO type - list of options
                        inputs[inp_name] = f"COMBO({len(inp_type)} options)"
                    elif isinstance(inp_type, str):
                        inputs[inp_name] = inp_type
                    else:
                        inputs[inp_name] = str(inp_type)
            node_summary["inputs"] = inputs

        # Output types - flatten nested lists and ensure strings
        raw_outputs = info.get("output", [])
        if raw_outputs:
            flat_outputs = []
            for o in raw_outputs:
                if isinstance(o, list):
                    flat_outputs.extend(str(x) for x in o)
                else:
                    flat_outputs.append(str(o))
            node_summary["outputs"] = flat_outputs

        # Sub-category for context
        if cat != top_cat:
            node_summary["subcategory"] = cat

        categories[top_cat].append(node_summary)

    # Sort categories and nodes
    sorted_cats = sorted(categories.keys())

    # Build markdown
    lines = [
        "---",
        "id: installed_nodes",
        "title: My Installed Nodes",
        "keywords: [nodes, custom nodes, installed, available]",
        "category: my_nodes",
        "priority: medium",
        "---",
        "",
        f"**{len(data)} nodes installed** across {len(sorted_cats)} categories.",
        f"Auto-generated from ComfyUI /object_info.",
        "",
    ]

    for cat in sorted_cats:
        nodes = sorted(categories[cat], key=lambda n: n["name"])
        lines.append(f"## {cat} ({len(nodes)} nodes)")
        lines.append("")

        for node in nodes:
            name = node["name"]
            display = node.get("display", "")
            display_str = f" ({display})" if display else ""

            inputs = node.get("inputs", {})
            outputs = node.get("outputs", [])

            inp_str = ", ".join(f"{k}:{v}" for k, v in inputs.items()) if inputs else ""
            out_str = ", ".join(str(o) for o in outputs) if outputs else ""

            parts = [f"- **{name}**{display_str}"]
            if inp_str:
                parts.append(f"  IN: {inp_str}")
            if out_str:
                parts.append(f"  OUT: {out_str}")

            lines.append(" | ".join(parts) if len(parts) == 1 else "\n  ".join(parts))

        lines.append("")

    out_path = AUTO_DIR / "installed_nodes.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Generated node knowledge: %d nodes in %s", len(data), out_path)
    return out_path


# -----------------------------------------------------------------------
# Dynamic model discovery
# -----------------------------------------------------------------------

# Known loader nodes and which COMBO input holds model filenames
_KNOWN_LOADERS = {
    "CheckpointLoaderSimple": ("ckpt_name", "checkpoints"),
    "CheckpointLoader": ("ckpt_name", "checkpoints"),
    "LoraLoader": ("lora_name", "loras"),
    "LoraLoaderModelOnly": ("lora_name", "loras"),
    "VAELoader": ("vae_name", "vae"),
    "ControlNetLoader": ("control_net_name", "controlnet"),
    "UpscaleModelLoader": ("model_name", "upscale_models"),
    "CLIPLoader": ("clip_name", "clip"),
    "DualCLIPLoader": ("clip_name1", "clip"),
    "UNETLoader": ("unet_name", "unet"),
    "DiffusionModelLoader": ("unet_name", "diffusion_models"),
    "StyleModelLoader": ("style_model_name", "style_models"),
    "GLIGENLoader": ("gligen_name", "gligen"),
    "HypernetworkLoader": ("hypernetwork_name", "hypernetworks"),
    "unCLIPCheckpointLoader": ("ckpt_name", "checkpoints"),
    "PhotoMakerLoader": ("photomaker_model_name", "photomaker"),
    "IPAdapterModelLoader": ("ipadapter_file", "ipadapter"),
    "InstantIDModelLoader": ("instantid_file", "instantid"),
    "CLIPVisionLoader": ("clip_name", "clip_vision"),
}


async def discover_all_model_types(comfyui_url: str = "http://127.0.0.1:8188") -> Dict[str, List[str]]:
    """Dynamically discover ALL model types by scanning loader nodes.

    This queries /object_info for every known loader node and extracts
    the COMBO options, which list all available model files (including
    those from extra_model_paths.yaml).

    Also scans /object_info for any unknown loader nodes with model-like
    COMBO inputs.

    Returns:
        Dict mapping model_type -> list of model filenames
    """
    all_models: Dict[str, List[str]] = {}

    try:
        async with aiohttp.ClientSession() as session:
            # Fetch full object_info once
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

    # 1. Check known loaders
    for node_class, (input_name, model_type) in _KNOWN_LOADERS.items():
        node_info = all_nodes.get(node_class)
        if not node_info:
            continue

        required = node_info.get("input", {}).get("required", {})
        optional = node_info.get("input", {}).get("optional", {})

        # Check both required and optional inputs
        for inputs in [required, optional]:
            inp_def = inputs.get(input_name)
            if inp_def and isinstance(inp_def, list) and len(inp_def) > 0:
                options = inp_def[0]
                if isinstance(options, list):
                    existing = all_models.get(model_type, [])
                    # Merge without duplicates
                    existing_set = set(existing)
                    for name in options:
                        if isinstance(name, str) and name not in existing_set:
                            existing.append(name)
                            existing_set.add(name)
                    all_models[model_type] = existing

    # 2. Auto-discover unknown loaders
    # Look for nodes with "Loader" in the name that have COMBO inputs
    # pointing to model files
    for node_class, node_info in all_nodes.items():
        # Skip already-known loaders
        if node_class in _KNOWN_LOADERS:
            continue

        # Only check nodes that look like loaders
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

            # Check if options look like model filenames
            sample = options[0] if options else ""
            if isinstance(sample, str) and any(
                sample.endswith(ext) for ext in (".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".onnx")
            ):
                # Determine category from input name
                category = _guess_model_category(inp_name, node_class)
                existing = all_models.get(category, [])
                existing_set = set(existing)
                for name in options:
                    if isinstance(name, str) and name not in existing_set:
                        existing.append(name)
                        existing_set.add(name)
                all_models[category] = existing
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
        "priority: medium",
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
