"""Model metadata scanner.

Reads .metadata.json files (created by LoRA Manager and similar tools)
and safetensors file headers to extract rich model information like
base model type, trigger words, recommended settings, and CivitAI data.
"""

import json
import logging
import struct
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("luna_core.model_metadata")

# Cache: filename -> metadata dict
_metadata_cache: Dict[str, Dict[str, Any]] = {}
_cache_loaded = False


def is_cache_loaded() -> bool:
    """Check if the metadata cache has been populated."""
    return _cache_loaded


def clear_cache():
    """Clear the metadata cache (e.g., on reload)."""
    global _metadata_cache, _cache_loaded
    _metadata_cache.clear()
    _cache_loaded = False


def scan_metadata_files(model_dirs: List[str]) -> Dict[str, Dict[str, Any]]:
    """Scan directories for .metadata.json files next to model files.

    Args:
        model_dirs: List of directory paths to scan recursively.

    Returns:
        Dict mapping model filename -> metadata dict with normalized fields.
    """
    global _metadata_cache, _cache_loaded

    if _cache_loaded:
        return _metadata_cache

    results = {}

    for dir_path in model_dirs:
        p = Path(dir_path)
        if not p.exists():
            continue

        # Find all .metadata.json files recursively
        for meta_file in p.rglob("*.metadata.json"):
            try:
                raw = json.loads(meta_file.read_text(encoding="utf-8"))
                normalized = _normalize_metadata(raw, meta_file)
                if normalized:
                    # Key by the model filename (without .metadata.json)
                    model_name = meta_file.name.replace(".metadata.json", "")
                    results[model_name] = normalized

                    # Also store with relative path using forward slashes
                    try:
                        rel = meta_file.relative_to(p)
                        rel_model = str(rel).replace(".metadata.json", "").replace("\\", "/")
                        results[rel_model] = normalized
                    except ValueError:
                        pass

            except (json.JSONDecodeError, OSError) as e:
                logger.debug("Could not read %s: %s", meta_file, e)
                continue

    _metadata_cache = results
    # Only mark as loaded if we actually scanned directories
    # If dirs were empty/invalid, allow retry on next call
    if model_dirs:
        _cache_loaded = True
    logger.info("Loaded %d model metadata files from %d directories", len(results), len(model_dirs))
    return results


def get_model_metadata(model_name: str) -> Optional[Dict[str, Any]]:
    """Get metadata for a specific model by filename.

    Tries exact match first, then normalized path match, then fuzzy.
    """
    if not _metadata_cache:
        return None

    # Normalize path separators for consistent matching
    normalized = model_name.replace("\\", "/")

    # Exact match (try both original and normalized)
    if model_name in _metadata_cache:
        return _metadata_cache[model_name]
    if normalized in _metadata_cache:
        return _metadata_cache[normalized]

    # Try basename only (e.g. "lora.safetensors" from "QwenDetails/lora.safetensors")
    basename = normalized.rsplit("/", 1)[-1]
    if basename in _metadata_cache:
        return _metadata_cache[basename]

    # Strip extension and try
    stem = Path(basename).stem
    if stem in _metadata_cache:
        return _metadata_cache[stem]

    # Normalized fuzzy match — compare with forward slashes on both sides
    name_lower = normalized.lower()
    basename_lower = basename.lower()
    for key, meta in _metadata_cache.items():
        key_norm = key.replace("\\", "/").lower()
        key_basename = key_norm.rsplit("/", 1)[-1]
        # Match on basename (most reliable)
        if basename_lower == key_basename:
            return meta
        # Substring match
        if name_lower in key_norm or key_norm in name_lower:
            return meta

    return None


def get_all_base_models() -> Dict[str, List[str]]:
    """Group all known models by their base model type.

    Returns:
        Dict like {"SDXL 1.0": ["model1.safetensors", ...], "Illustrious": [...]}
    """
    groups: Dict[str, List[str]] = {}
    for model_name, meta in _metadata_cache.items():
        # Skip relative path duplicates (only use filename keys)
        if "/" in model_name or "\\" in model_name:
            continue
        base = meta.get("base_model", "Unknown")
        if base not in groups:
            groups[base] = []
        groups[base].append(model_name)
    return groups


def _normalize_metadata(raw: Dict[str, Any], meta_path: Path) -> Optional[Dict[str, Any]]:
    """Normalize a .metadata.json into a clean, consistent format.

    Extracts the most useful fields regardless of the source format.
    """
    result: Dict[str, Any] = {}

    # Base model type (most important)
    result["base_model"] = (
        raw.get("base_model")
        or _deep_get(raw, "civitai", "baseModel")
        or "Unknown"
    )

    # Model name
    result["model_name"] = (
        raw.get("model_name")
        or _deep_get(raw, "civitai", "model", "name")
        or raw.get("file_name", "")
    )

    # Model type (LORA, Checkpoint, TextualInversion, etc.)
    result["model_type"] = (
        _deep_get(raw, "civitai", "model", "type")
        or "Unknown"
    )

    # Trigger words
    trained_words = _deep_get(raw, "civitai", "trainedWords") or []
    if isinstance(trained_words, list) and trained_words:
        result["trigger_words"] = trained_words

    # Tags
    tags = _deep_get(raw, "civitai", "model", "tags") or []
    if isinstance(tags, list) and tags:
        result["tags"] = tags

    # CivitAI IDs for reference
    civitai_model_id = _deep_get(raw, "civitai", "modelId")
    civitai_version_id = _deep_get(raw, "civitai", "id")
    if civitai_model_id:
        result["civitai_model_id"] = civitai_model_id
        result["civitai_url"] = f"https://civitai.com/models/{civitai_model_id}"
    if civitai_version_id:
        result["civitai_version_id"] = civitai_version_id

    # Version info
    version_name = _deep_get(raw, "civitai", "name")
    if version_name:
        result["version"] = version_name

    # File size
    size = raw.get("size")
    if size and isinstance(size, (int, float)):
        result["size_mb"] = round(size / (1024 * 1024), 1)

    # SHA256 hash
    sha256 = raw.get("sha256")
    if sha256:
        result["sha256"] = sha256

    # Usage tips
    usage_tips = raw.get("usage_tips")
    if usage_tips:
        if isinstance(usage_tips, str):
            try:
                usage_tips = json.loads(usage_tips)
            except json.JSONDecodeError:
                usage_tips = None
        if isinstance(usage_tips, dict):
            result["usage_tips"] = usage_tips

    # Extract example generation parameters from CivitAI images
    images = _deep_get(raw, "civitai", "images") or []
    example_params = _extract_best_example(images)
    if example_params:
        result["example_params"] = example_params

    # Description (truncated)
    desc = _deep_get(raw, "civitai", "model", "description") or ""
    if desc:
        # Strip HTML tags for plain text
        import re
        desc = re.sub(r"<[^>]+>", " ", desc)
        desc = re.sub(r"\s+", " ", desc).strip()
        if len(desc) > 300:
            desc = desc[:300] + "..."
        result["description"] = desc

    return result if result.get("model_name") else None


def _extract_best_example(images: List[dict]) -> Optional[Dict[str, Any]]:
    """Extract the best example generation parameters from CivitAI images.

    Picks the first image that has full generation metadata.
    """
    for img in images:
        meta = img.get("meta")
        if not meta or not isinstance(meta, dict):
            continue

        # Skip if no prompt
        prompt = meta.get("prompt")
        if not prompt:
            continue

        params: Dict[str, Any] = {"prompt": prompt}

        neg = meta.get("negativePrompt")
        if neg:
            params["negative_prompt"] = neg

        # Numeric settings
        for key, out_key in [
            ("steps", "steps"),
            ("cfgScale", "cfg"),
            ("clipSkip", "clip_skip"),
            ("seed", "seed"),
        ]:
            val = meta.get(key)
            if val is not None:
                params[out_key] = val

        # String settings
        for key in ["sampler", "Model", "VAE", "scheduler"]:
            val = meta.get(key)
            if val:
                params[key.lower()] = val

        # LoRA resources with weights
        resources = meta.get("resources")
        if resources and isinstance(resources, list):
            loras = []
            for r in resources:
                if r.get("type") == "lora":
                    lora_info = {"name": r.get("name", "")}
                    if "weight" in r:
                        lora_info["weight"] = r["weight"]
                    loras.append(lora_info)
            if loras:
                params["loras_used"] = loras

        return params

    return None


def _deep_get(d: dict, *keys):
    """Safely navigate nested dicts."""
    for key in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(key)
        if d is None:
            return None
    return d


def read_safetensors_header(filepath: str) -> Optional[Dict[str, Any]]:
    """Read metadata from a safetensors file header.

    Safetensors files start with an 8-byte little-endian integer
    indicating the header size, followed by a JSON header.
    """
    try:
        with open(filepath, "rb") as f:
            # Read header size (first 8 bytes, little-endian uint64)
            header_size_bytes = f.read(8)
            if len(header_size_bytes) < 8:
                return None
            header_size = struct.unpack("<Q", header_size_bytes)[0]

            # Sanity check — header shouldn't be larger than 10MB
            if header_size > 10 * 1024 * 1024:
                return None

            header_json = f.read(header_size)
            header = json.loads(header_json)

        # Extract __metadata__ section if present
        meta = header.get("__metadata__", {})
        if not meta:
            return None

        result = {}

        # Common safetensors metadata keys
        if "ss_base_model_version" in meta:
            result["base_model"] = meta["ss_base_model_version"]
        if "ss_network_module" in meta:
            result["network_type"] = meta["ss_network_module"]
        if "ss_resolution" in meta:
            result["training_resolution"] = meta["ss_resolution"]
        if "ss_num_train_images" in meta:
            result["training_images"] = meta["ss_num_train_images"]
        if "ss_tag_frequency" in meta:
            # This contains the tags used in training — useful for trigger words
            try:
                tag_freq = json.loads(meta["ss_tag_frequency"]) if isinstance(meta["ss_tag_frequency"], str) else meta["ss_tag_frequency"]
                if isinstance(tag_freq, dict):
                    # Get top tags across all datasets
                    all_tags = {}
                    for dataset_tags in tag_freq.values():
                        if isinstance(dataset_tags, dict):
                            for tag, count in dataset_tags.items():
                                count_val = int(count) if isinstance(count, (int, float, str)) else 0
                                all_tags[tag] = all_tags.get(tag, 0) + count_val
                    # Top 10 most frequent tags
                    sorted_tags = sorted(all_tags.items(), key=lambda x: x[1], reverse=True)[:10]
                    result["top_training_tags"] = [t[0] for t in sorted_tags]
            except (json.JSONDecodeError, ValueError):
                pass

        if "modelspec.title" in meta:
            result["model_name"] = meta["modelspec.title"]
        if "modelspec.architecture" in meta:
            result["architecture"] = meta["modelspec.architecture"]

        return result if result else None

    except (OSError, json.JSONDecodeError, struct.error) as e:
        logger.debug("Could not read safetensors header from %s: %s", filepath, e)
        return None
