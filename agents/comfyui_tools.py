"""ComfyUI tool definitions for agent function calling.

Provides tools that let LLMs query ComfyUI's node registry, available
models, and current workflow on-demand instead of stuffing everything
into the system prompt.  Also provides workflow manipulation tools
so the agent can surgically modify the user's current workflow.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from .tools import ToolDefinition, ToolParameter, ToolRegistry

logger = logging.getLogger("luna_core.tools")

# Keep a module-level reference so tool closures can access it
_node_registry = None
_system_monitor = None
_workflow_registry = None


def setup_tools(node_registry, system_monitor=None, workflow_registry=None) -> List[ToolDefinition]:
    """Create and register ComfyUI tools.

    Args:
        node_registry: A NodeRegistry instance (from validation.node_registry)
        system_monitor: Optional SystemMonitor class for model listing
        workflow_registry: Optional WorkflowRegistry for template/workflow search

    Returns:
        List of registered ToolDefinition objects.
    """
    global _node_registry, _system_monitor, _workflow_registry
    _node_registry = node_registry
    _system_monitor = system_monitor
    _workflow_registry = workflow_registry

    tools = [
        _make_get_node_types(),
        _make_get_node_info(),
        _make_get_available_models(),
        _make_get_model_metadata(),
        _make_get_current_workflow(),
        _make_modify_node_input(),
        _make_add_node(),
        _make_remove_node(),
        _make_connect_nodes(),
        _make_search_workflows(),
        _make_get_workflow_template(),
        _make_queue_prompt(),
        _make_get_execution_errors(),
    ]

    ToolRegistry.clear()
    for tool in tools:
        ToolRegistry.register(tool)

    return tools


# ---------------------------------------------------------------------------
# Tool: get_node_types
# ---------------------------------------------------------------------------

def _make_get_node_types() -> ToolDefinition:
    async def handler(search: str = "", category: str = "", limit: int = 50) -> str:
        if not _node_registry or not _node_registry.is_loaded:
            await _node_registry.fetch()
        if not _node_registry or not _node_registry.is_loaded:
            return json.dumps({"error": "Node registry not available. Is ComfyUI running?"})

        all_types = _node_registry.get_all_class_types()
        results = []

        for ct in all_types:
            node = _node_registry.get_node(ct)
            if not node:
                continue
            if search and search.lower() not in ct.lower() and search.lower() not in (node.display_name or "").lower():
                continue
            if category and category.lower() not in (node.category or "").lower():
                continue
            results.append({
                "class_type": ct,
                "display_name": node.display_name,
                "category": node.category,
                "outputs": node.output_types,
            })
            if len(results) >= limit:
                break

        return json.dumps({
            "total_available": len(all_types),
            "returned": len(results),
            "nodes": results,
        })

    return ToolDefinition(
        name="get_node_types",
        description="Search or browse installed ComfyUI node types. Use this to find which nodes are available before building a workflow. You can filter by name or category.",
        parameters=[
            ToolParameter(name="search", type="string",
                          description="Search term to filter nodes by class_type or display_name (case-insensitive). Leave empty to browse.",
                          required=False),
            ToolParameter(name="category", type="string",
                          description="Filter by category (e.g. 'sampling', 'loaders', 'conditioning'). Case-insensitive partial match.",
                          required=False),
            ToolParameter(name="limit", type="integer",
                          description="Maximum number of results to return (default 50).",
                          required=False),
        ],
        handler=handler,
    )


# ---------------------------------------------------------------------------
# Tool: get_node_info
# ---------------------------------------------------------------------------

def _make_get_node_info() -> ToolDefinition:
    async def handler(class_type: str) -> str:
        if not _node_registry or not _node_registry.is_loaded:
            await _node_registry.fetch()
        if not _node_registry or not _node_registry.is_loaded:
            return json.dumps({"error": "Node registry not available."})

        node = _node_registry.get_node(class_type)
        if not node:
            suggestions = _node_registry.suggest_similar(class_type)
            return json.dumps({
                "error": f"Node '{class_type}' not found.",
                "suggestions": suggestions,
            })

        required_inputs = {}
        for name, inp in node.inputs_required.items():
            entry = {"type": inp.type, "required": True}
            if inp.default is not None:
                entry["default"] = inp.default
            if inp.min_val is not None:
                entry["min"] = inp.min_val
            if inp.max_val is not None:
                entry["max"] = inp.max_val
            if inp.options:
                entry["options"] = inp.options[:30]  # cap long combo lists
            required_inputs[name] = entry

        optional_inputs = {}
        for name, inp in node.inputs_optional.items():
            entry = {"type": inp.type, "required": False}
            if inp.default is not None:
                entry["default"] = inp.default
            if inp.min_val is not None:
                entry["min"] = inp.min_val
            if inp.max_val is not None:
                entry["max"] = inp.max_val
            if inp.options:
                entry["options"] = inp.options[:30]
            optional_inputs[name] = entry

        return json.dumps({
            "class_type": node.class_type,
            "display_name": node.display_name,
            "category": node.category,
            "description": node.description,
            "inputs_required": required_inputs,
            "inputs_optional": optional_inputs,
            "output_types": node.output_types,
            "output_names": node.output_names,
        })

    return ToolDefinition(
        name="get_node_info",
        description="Get full input/output specification for a specific ComfyUI node type. Use this to check exact parameter names, types, defaults, and valid ranges before creating or modifying a workflow.",
        parameters=[
            ToolParameter(name="class_type", type="string",
                          description="The exact class_type of the node (e.g. 'KSampler', 'CheckpointLoaderSimple').",
                          required=True),
        ],
        handler=handler,
    )


# ---------------------------------------------------------------------------
# Tool: get_available_models (dynamic discovery from all loader nodes)
# ---------------------------------------------------------------------------

# Cache for dynamically discovered models
_discovered_models: Optional[Dict[str, List[str]]] = None


async def _discover_models() -> Dict[str, List[str]]:
    """Discover all model types by querying ComfyUI loader nodes."""
    global _discovered_models
    if _discovered_models is not None:
        return _discovered_models

    try:
        from ..knowledge.auto_generator import discover_all_model_types
        result = await discover_all_model_types()
        if result:  # Only cache if we actually found models
            _discovered_models = result
            return _discovered_models
    except Exception as e:
        logger.warning("Model discovery failed: %s", e)

    # Fallback to SystemMonitor
    if _system_monitor:
        try:
            models = await _system_monitor.get_available_models()
            if models:
                _discovered_models = models
                return models
        except Exception:
            pass

    # Return empty but don't cache — allow retry next time
    return {}


def reset_model_cache():
    """Reset the model discovery cache (call on reload)."""
    global _discovered_models
    _discovered_models = None


def _make_get_available_models() -> ToolDefinition:
    async def handler(model_type: str = "checkpoints", search: str = "", folder: str = "") -> str:
        models = await _discover_models()

        if not models:
            return json.dumps({"error": "Could not discover models. Is ComfyUI running?"})

        key = model_type.lower().rstrip("s")  # Normalize: "controlnets" -> "controlnet"
        # Try exact match first, then normalized
        found = models.get(model_type.lower())
        if found is None:
            # Try without trailing 's' or with trailing 's'
            for k in models:
                if k.rstrip("s") == key or k == key + "s":
                    found = models[k]
                    break
        if found is None:
            found = []

        # Apply search filter (case-insensitive substring match on filename)
        if search:
            search_lower = search.lower()
            found = [m for m in found if search_lower in m.lower()]

        # Apply folder filter (match subfolder prefix)
        if folder:
            folder_lower = folder.lower().replace("\\", "/")
            found = [m for m in found
                     if folder_lower in m.replace("\\", "/").lower().rsplit("/", 1)[0]
                     if "/" in m.replace("\\", "/") or "\\" in m]

        # Higher limit when filtering (filtered results are smaller)
        max_response = 200 if (search or folder) else 100
        if len(found) > max_response:
            return json.dumps({
                "model_type": model_type,
                "total": len(found),
                "showing": max_response,
                "models": found[:max_response],
                "note": f"Showing first {max_response} of {len(found)}. Use 'search' to narrow results.",
                "available_types": list(models.keys()),
            })

        return json.dumps({
            "model_type": model_type,
            "count": len(found),
            "models": found,
            "available_types": list(models.keys()),
        })

    return ToolDefinition(
        name="get_available_models",
        description="List models available in the user's ComfyUI installation. Discovers ALL model types dynamically from loader nodes, including models from extra_model_paths.yaml. Use 'search' to find specific models by name, or 'folder' to filter by subfolder.",
        parameters=[
            ToolParameter(name="model_type", type="string",
                          description="Type of model to list. Common types: 'checkpoints', 'loras', 'vae', 'controlnet', 'upscale_models', 'clip', 'clip_vision', 'unet', 'diffusion_models', 'embeddings', 'ipadapter'. Call without arguments to see all available types.",
                          required=False),
            ToolParameter(name="search", type="string",
                          description="Search filter — case-insensitive substring match on filename (e.g. 'pony', 'illustrious', 'realvis'). Use this when the full list is truncated or you're looking for a specific model.",
                          required=False),
            ToolParameter(name="folder", type="string",
                          description="Filter by subfolder name (e.g. 'Pony', 'QwenDetails', 'Illustrious'). Only returns models in that subfolder.",
                          required=False),
        ],
        handler=handler,
    )


# ---------------------------------------------------------------------------
# Tool: get_model_metadata (rich info from .metadata.json files)
# ---------------------------------------------------------------------------

def _make_get_model_metadata() -> ToolDefinition:
    async def handler(model_name: str) -> str:
        from ..system.model_metadata import get_model_metadata as _get_meta, scan_metadata_files, is_cache_loaded

        # Lazy-initialize metadata cache on first call
        if not is_cache_loaded():
            try:
                from ..knowledge.auto_generator import _find_model_directories
                model_dirs = _find_model_directories()
                if model_dirs:
                    scan_metadata_files(model_dirs)
                    logger.info("Initialized model metadata cache from %d directories", len(model_dirs))
            except Exception as e:
                logger.warning("Could not initialize metadata cache: %s", e)

        meta = _get_meta(model_name)
        if not meta:
            return json.dumps({
                "error": f"No metadata found for '{model_name}'. This model may not have a .metadata.json file (created by LoRA Manager or similar tools).",
                "tip": "You can still use this model — just check its base model type from the filename or try it in a workflow.",
            })

        # Build a clean response with the most useful fields
        result = {
            "model_name": meta.get("model_name", model_name),
            "base_model": meta.get("base_model", "Unknown"),
            "model_type": meta.get("model_type", "Unknown"),
        }

        if meta.get("trigger_words"):
            result["trigger_words"] = meta["trigger_words"]

        if meta.get("tags"):
            result["tags"] = meta["tags"]

        if meta.get("description"):
            result["description"] = meta["description"]

        if meta.get("version"):
            result["version"] = meta["version"]

        if meta.get("civitai_url"):
            result["civitai_url"] = meta["civitai_url"]

        if meta.get("usage_tips"):
            result["usage_tips"] = meta["usage_tips"]

        # Example generation parameters (from CivitAI images)
        if meta.get("example_params"):
            ep = meta["example_params"]
            result["recommended_settings"] = {}
            for key in ("steps", "cfg", "sampler", "clip_skip", "scheduler"):
                if key in ep:
                    result["recommended_settings"][key] = ep[key]
            if "prompt" in ep:
                # Truncate long prompts
                prompt = ep["prompt"]
                result["example_prompt"] = prompt[:500] + "..." if len(prompt) > 500 else prompt
            if "negative_prompt" in ep:
                neg = ep["negative_prompt"]
                result["example_negative"] = neg[:300] + "..." if len(neg) > 300 else neg
            if "loras_used" in ep:
                result["example_loras"] = ep["loras_used"]

        return json.dumps(result)

    return ToolDefinition(
        name="get_model_metadata",
        description="Get rich metadata for a specific model — base model type, trigger words, recommended settings, CivitAI tags, and example prompts. Uses .metadata.json files from LoRA Manager. Essential for knowing how to prompt correctly with a model.",
        parameters=[
            ToolParameter(name="model_name", type="string",
                          description="The model filename (e.g. 'JuggerCineXL2.safetensors') or partial name. Metadata comes from .metadata.json files created by LoRA Manager.",
                          required=True),
        ],
        handler=handler,
    )


# ---------------------------------------------------------------------------
# Tool: get_current_workflow
# ---------------------------------------------------------------------------

# The current workflow is injected by the controller before each chat turn
_current_workflow = None
# Track in-place modifications for direct canvas application
_pending_modifications: List[Dict[str, Any]] = []


def set_current_workflow(workflow: Optional[dict]) -> None:
    """Called by the controller to make the current workflow available to tools."""
    global _current_workflow, _pending_modifications
    _current_workflow = workflow
    _pending_modifications = []  # Reset on each new chat turn


def get_pending_modifications() -> List[Dict[str, Any]]:
    """Get and clear pending modifications."""
    global _pending_modifications
    mods = list(_pending_modifications)
    _pending_modifications = []
    return mods


def _make_get_current_workflow() -> ToolDefinition:
    async def handler() -> str:
        if not _current_workflow:
            return json.dumps({"error": "No workflow is currently loaded in ComfyUI."})

        nodes = _current_workflow if isinstance(_current_workflow, dict) else {}
        summary = []
        for node_id, node_data in nodes.items():
            ct = node_data.get("class_type", "Unknown")
            title = (node_data.get("_meta") or {}).get("title", ct)
            inputs = node_data.get("inputs", {})
            # Include inputs in summary for context (but compact connections)
            compact_inputs = {}
            for k, v in inputs.items():
                if isinstance(v, list) and len(v) == 2:
                    compact_inputs[k] = f"[node {v[0]}, slot {v[1]}]"
                else:
                    compact_inputs[k] = v
            summary.append({
                "id": node_id,
                "class_type": ct,
                "title": title,
                "inputs": compact_inputs,
            })

        # For large workflows, skip full workflow dump to save context
        MAX_NODES_FULL_DUMP = 30
        if len(nodes) > MAX_NODES_FULL_DUMP:
            return json.dumps({
                "node_count": len(nodes),
                "nodes": summary,
                "note": f"Large workflow ({len(nodes)} nodes). Node inputs shown in summary. Use modify_node_input() to change specific nodes by ID.",
            })

        return json.dumps({
            "node_count": len(nodes),
            "nodes": summary,
            "workflow": _current_workflow,
        })

    return ToolDefinition(
        name="get_current_workflow",
        description="Get the user's current ComfyUI workflow. Returns all nodes with their IDs, types, and full configuration. Use this to understand the existing workflow before suggesting modifications.",
        parameters=[],
        handler=handler,
    )


# ---------------------------------------------------------------------------
# Helper: validate a value against node_info
# ---------------------------------------------------------------------------

async def _validate_input_value(class_type: str, input_name: str, value: Any) -> Optional[str]:
    """Validate that a value is acceptable for a node input.

    Returns an error string if invalid, None if valid.
    """
    if not _node_registry or not _node_registry.is_loaded:
        return None  # Can't validate, allow it

    node = _node_registry.get_node(class_type)
    if not node:
        return None  # Unknown node, allow it

    # Find the input definition
    inp = node.inputs_required.get(input_name) or node.inputs_optional.get(input_name)
    if not inp:
        return f"Input '{input_name}' not found on node '{class_type}'. Available inputs: {list(node.inputs_required.keys()) + list(node.inputs_optional.keys())}"

    # Skip validation for connection-type inputs (MODEL, CLIP, etc.)
    if inp.type in ("MODEL", "CLIP", "VAE", "CONDITIONING", "LATENT", "IMAGE",
                     "MASK", "CONTROL_NET", "UPSCALE_MODEL", "SIGMAS", "NOISE",
                     "SAMPLER", "GUIDER", "BBOX_DETECTOR", "SEGM_DETECTOR",
                     "SAM_MODEL", "DETAILER_PIPE", "BASIC_PIPE"):
        return None  # These are node connections, not direct values

    # Validate COMBO options
    if inp.type == "COMBO" and inp.options:
        if isinstance(value, str) and value not in inp.options:
            return f"Value '{value}' not in valid options for '{input_name}'. Valid: {inp.options[:20]}"

    # Validate numeric ranges
    if inp.type in ("INT", "FLOAT"):
        try:
            num_val = float(value)
            if inp.min_val is not None and num_val < inp.min_val:
                return f"Value {value} below minimum {inp.min_val} for '{input_name}'"
            if inp.max_val is not None and num_val > inp.max_val:
                return f"Value {value} above maximum {inp.max_val} for '{input_name}'"
        except (TypeError, ValueError):
            pass  # Not a number, might be a connection

    return None


# ---------------------------------------------------------------------------
# Tool: modify_node_input
# ---------------------------------------------------------------------------

def _make_modify_node_input() -> ToolDefinition:
    async def handler(node_id: str, input_name: str, value: str) -> str:
        global _current_workflow
        if not _current_workflow:
            return json.dumps({"error": "No workflow loaded. Ask the user to check 'Include current workflow'."})

        if node_id not in _current_workflow:
            available = list(_current_workflow.keys())
            return json.dumps({"error": f"Node '{node_id}' not found. Available node IDs: {available}"})

        node = _current_workflow[node_id]
        class_type = node.get("class_type", "Unknown")

        # Parse the value to the correct type
        parsed_value: Any = value
        try:
            # Try int first, then float, then keep as string
            if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
                parsed_value = int(value)
            else:
                parsed_value = float(value)
        except (ValueError, AttributeError):
            # Check for booleans
            if isinstance(value, str):
                if value.lower() == "true":
                    parsed_value = True
                elif value.lower() == "false":
                    parsed_value = False

        # Validate against node info
        validation_error = await _validate_input_value(class_type, input_name, parsed_value)
        if validation_error:
            return json.dumps({"error": validation_error, "node_id": node_id, "class_type": class_type})

        # Get old value for the response
        old_value = node.get("inputs", {}).get(input_name, "<not set>")

        # Apply the change
        if "inputs" not in node:
            node["inputs"] = {}
        node["inputs"][input_name] = parsed_value

        # Track modification for direct canvas application
        # Skip connection inputs (lists like [node_id, slot]) — those are links, not widgets
        if not isinstance(parsed_value, list):
            _pending_modifications.append({
                "action": "modify",
                "node_id": node_id,
                "input_name": input_name,
                "value": parsed_value,
            })

        return json.dumps({
            "success": True,
            "node_id": node_id,
            "class_type": class_type,
            "input_name": input_name,
            "old_value": str(old_value),
            "new_value": str(parsed_value),
        })

    return ToolDefinition(
        name="modify_node_input",
        description="Modify a specific input/setting on a node in the current workflow. Use get_current_workflow() first to find node IDs, and get_node_info() to check valid input names and ranges. The modified workflow is returned for the user to apply.",
        parameters=[
            ToolParameter(name="node_id", type="string",
                          description="The node ID to modify (e.g. '5', '12'). Get this from get_current_workflow().",
                          required=True),
            ToolParameter(name="input_name", type="string",
                          description="The exact input parameter name (e.g. 'steps', 'cfg', 'denoise', 'sampler_name'). Get this from get_node_info().",
                          required=True),
            ToolParameter(name="value", type="string",
                          description="The new value. Numbers, booleans ('true'/'false'), and strings are auto-detected.",
                          required=True),
        ],
        handler=handler,
    )


# ---------------------------------------------------------------------------
# Tool: add_node
# ---------------------------------------------------------------------------

def _make_add_node() -> ToolDefinition:
    async def handler(class_type: str, inputs: str, title: str = "") -> str:
        global _current_workflow
        if not _current_workflow:
            return json.dumps({"error": "No workflow loaded. Ask the user to check 'Include current workflow'."})

        # Verify node type exists
        if _node_registry and _node_registry.is_loaded:
            if not _node_registry.node_exists(class_type):
                suggestions = _node_registry.suggest_similar(class_type)
                return json.dumps({
                    "error": f"Node type '{class_type}' not found in registry.",
                    "suggestions": suggestions,
                })

        # Parse inputs JSON
        try:
            parsed_inputs = json.loads(inputs)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON for inputs: {e}"})

        if not isinstance(parsed_inputs, dict):
            return json.dumps({"error": "Inputs must be a JSON object/dict."})

        # Calculate next node ID
        try:
            next_id = str(max(int(k) for k in _current_workflow.keys()) + 1)
        except (ValueError, TypeError):
            next_id = str(len(_current_workflow) + 1)

        # Add the node
        _current_workflow[next_id] = {
            "class_type": class_type,
            "inputs": parsed_inputs,
            "_meta": {"title": title or class_type},
        }

        # Track for direct canvas application
        _pending_modifications.append({
            "action": "add",
            "node_id": next_id,
            "class_type": class_type,
            "inputs": parsed_inputs,
            "title": title or class_type,
        })

        return json.dumps({
            "success": True,
            "node_id": next_id,
            "class_type": class_type,
            "title": title or class_type,
        })

    return ToolDefinition(
        name="add_node",
        description="Add a new node to the current workflow. Use get_node_types() to find the right node and get_node_info() to check required inputs. Connections to other nodes use format [\"source_node_id\", output_slot_index].",
        parameters=[
            ToolParameter(name="class_type", type="string",
                          description="The node class_type (e.g. 'KSampler', 'LoraLoader'). Must be a valid installed node.",
                          required=True),
            ToolParameter(name="inputs", type="string",
                          description='JSON string of input values. Example: \'{"model": ["1", 0], "steps": 20, "cfg": 7.0}\'',
                          required=True),
            ToolParameter(name="title", type="string",
                          description="Optional display title for the node.",
                          required=False),
        ],
        handler=handler,
    )


# ---------------------------------------------------------------------------
# Tool: remove_node
# ---------------------------------------------------------------------------

def _make_remove_node() -> ToolDefinition:
    async def handler(node_id: str) -> str:
        global _current_workflow
        if not _current_workflow:
            return json.dumps({"error": "No workflow loaded."})

        if node_id not in _current_workflow:
            available = list(_current_workflow.keys())
            return json.dumps({"error": f"Node '{node_id}' not found. Available: {available}"})

        removed_node = _current_workflow[node_id]
        class_type = removed_node.get("class_type", "Unknown")

        # Remove the node
        del _current_workflow[node_id]

        # Clean up references to this node in other nodes' inputs
        broken_refs = []
        for other_id, node in _current_workflow.items():
            inputs = node.get("inputs", {})
            for input_name, value in list(inputs.items()):
                if isinstance(value, list) and len(value) == 2 and str(value[0]) == node_id:
                    del inputs[input_name]
                    broken_refs.append(f"Node {other_id}.{input_name}")

        # Track for direct canvas application
        _pending_modifications.append({
            "action": "remove",
            "node_id": node_id,
        })

        return json.dumps({
            "success": True,
            "removed_node_id": node_id,
            "removed_class_type": class_type,
            "broken_connections_cleaned": broken_refs,
            "remaining_nodes": len(_current_workflow),
        })

    return ToolDefinition(
        name="remove_node",
        description="Remove a node from the current workflow. Automatically cleans up any connections that referenced this node. Use get_current_workflow() first to find the node ID.",
        parameters=[
            ToolParameter(name="node_id", type="string",
                          description="The node ID to remove.",
                          required=True),
        ],
        handler=handler,
    )


# ---------------------------------------------------------------------------
# Tool: connect_nodes
# ---------------------------------------------------------------------------

def _make_connect_nodes() -> ToolDefinition:
    async def handler(source_node_id: str, source_output_slot: str, target_node_id: str, target_input_name: str) -> str:
        global _current_workflow
        if not _current_workflow:
            return json.dumps({"error": "No workflow loaded."})

        if source_node_id not in _current_workflow:
            return json.dumps({"error": f"Source node '{source_node_id}' not found."})
        if target_node_id not in _current_workflow:
            return json.dumps({"error": f"Target node '{target_node_id}' not found."})

        try:
            slot = int(source_output_slot)
        except ValueError:
            return json.dumps({"error": f"source_output_slot must be an integer, got '{source_output_slot}'"})

        # Validate output slot exists
        source_class = _current_workflow[source_node_id].get("class_type", "")
        target_class = _current_workflow[target_node_id].get("class_type", "")

        if _node_registry and _node_registry.is_loaded:
            source_node_def = _node_registry.get_node(source_class)
            if source_node_def:
                if slot >= len(source_node_def.output_types):
                    return json.dumps({
                        "error": f"Source node '{source_class}' only has {len(source_node_def.output_types)} outputs (slots 0-{len(source_node_def.output_types)-1}). Requested slot {slot}.",
                        "available_outputs": list(zip(source_node_def.output_names, source_node_def.output_types)),
                    })

                # Validate type compatibility
                output_type = source_node_def.output_types[slot]
                target_node_def = _node_registry.get_node(target_class)
                if target_node_def:
                    target_inp = (target_node_def.inputs_required.get(target_input_name)
                                  or target_node_def.inputs_optional.get(target_input_name))
                    if target_inp and target_inp.type not in ("*", "COMBO", "STRING"):
                        # Check if types are compatible (exact match or wildcard)
                        out_type = output_type if isinstance(output_type, str) else str(output_type)
                        if out_type != target_inp.type and out_type != "*":
                            return json.dumps({
                                "error": f"Type mismatch: source outputs '{out_type}' but target input '{target_input_name}' expects '{target_inp.type}'.",
                            })

        # Apply the connection
        target_node = _current_workflow[target_node_id]
        if "inputs" not in target_node:
            target_node["inputs"] = {}
        target_node["inputs"][target_input_name] = [source_node_id, slot]

        # Track for direct canvas application
        _pending_modifications.append({
            "action": "connect",
            "source_node_id": source_node_id,
            "source_output_slot": slot,
            "target_node_id": target_node_id,
            "target_input_name": target_input_name,
        })

        return json.dumps({
            "success": True,
            "connection": f"{source_class}[{slot}] -> {target_class}.{target_input_name}",
        })

    return ToolDefinition(
        name="connect_nodes",
        description="Connect two nodes in the current workflow. Creates a link from a source node's output slot to a target node's input. Validates type compatibility when possible.",
        parameters=[
            ToolParameter(name="source_node_id", type="string",
                          description="ID of the source node.",
                          required=True),
            ToolParameter(name="source_output_slot", type="string",
                          description="Output slot index on the source node (0-based). Use get_node_info() to see available outputs.",
                          required=True),
            ToolParameter(name="target_node_id", type="string",
                          description="ID of the target node.",
                          required=True),
            ToolParameter(name="target_input_name", type="string",
                          description="Input name on the target node (e.g. 'model', 'clip', 'positive'). Use get_node_info() to see available inputs.",
                          required=True),
        ],
        handler=handler,
    )


# ---------------------------------------------------------------------------
# Tool: search_workflows (local user workflows + official templates)
# ---------------------------------------------------------------------------

def _make_search_workflows() -> ToolDefinition:
    async def handler(query: str = "", category: str = "", node_type: str = "", source: str = "") -> str:
        if not _workflow_registry:
            return json.dumps({"error": "Workflow registry not initialized."})

        if not _workflow_registry.is_loaded:
            _workflow_registry.load()

        # If no filters, show categories overview
        if not query and not category and not node_type and not source:
            categories = _workflow_registry.get_categories()
            # Count by source
            local_count = sum(1 for e in _workflow_registry._entries if e.source == "local")
            official_count = sum(1 for e in _workflow_registry._entries if e.source == "official")
            return json.dumps({
                "total_workflows": _workflow_registry.count,
                "local_workflows": local_count,
                "official_templates": official_count,
                "categories": categories,
                "tip": "Use 'source' filter: 'local' for user workflows, 'official' for Comfy-Org templates. Always check BOTH sources before building from scratch.",
            })

        results = _workflow_registry.search(query=query, category=category,
                                             node_type=node_type, limit=20)

        # Filter by source if specified
        if source:
            source_lower = source.lower()
            results = [r for r in results if source_lower in r.source.lower()]

        if not results:
            return json.dumps({
                "results": [],
                "tip": "No workflows matched. Try 'source: official' for Comfy-Org templates, or broader search terms.",
                "categories": _workflow_registry.get_categories(),
            })

        return json.dumps({
            "count": len(results),
            "workflows": [
                {
                    "name": r.name,
                    "category": r.category,
                    "source": r.source,
                    "node_count": r.node_count,
                    "key_nodes": [t for t in r.node_types if any(
                        kw in t.lower() for kw in
                        ("loader", "sampler", "ksampler", "wan", "flux",
                         "controlnet", "lora", "vae", "encode", "video",
                         "upscale", "animate", "qwen", "ltx", "hunyuan")
                    )][:8],
                    "path": r.path,
                }
                for r in results
            ],
            "tip": "Use get_workflow_template(path) to load a specific workflow as a starting point.",
        })

    return ToolDefinition(
        name="search_workflows",
        description="Search the user's saved workflows AND official Comfy-Org templates. IMPORTANT: Always search BOTH sources — use source='local' for user workflows and source='official' for official templates. Check both before building from scratch.",
        parameters=[
            ToolParameter(name="query", type="string",
                          description="Search text (matches name, category, node types). Leave empty to see categories overview.",
                          required=False),
            ToolParameter(name="category", type="string",
                          description="Filter by category/folder (e.g., 'FLUX', 'SDXL', 'WAN', 'ILLUSTRIOUS', 'QWEN', 'LTX2', 'UPSCALE', 'ZIMAGE'). Case-insensitive.",
                          required=False),
            ToolParameter(name="node_type", type="string",
                          description="Filter by node type used in workflow (e.g., 'LoraLoader', 'ControlNet', 'WAN'). Partial match.",
                          required=False),
            ToolParameter(name="source", type="string",
                          description="Filter by source: 'local' for user's saved workflows, 'official' for Comfy-Org templates. Leave empty to search both.",
                          required=False),
        ],
        handler=handler,
    )


# ---------------------------------------------------------------------------
# Tool: get_workflow_template (load a specific workflow)
# ---------------------------------------------------------------------------

def _make_get_workflow_template() -> ToolDefinition:
    async def handler(path: str) -> str:
        if not _workflow_registry:
            return json.dumps({"error": "Workflow registry not initialized."})

        workflow = _workflow_registry.get_workflow(path)
        if not workflow:
            return json.dumps({"error": f"Could not load workflow from: {path}"})

        # For UI-format workflows, extract a useful summary instead of dumping everything
        if "nodes" in workflow and isinstance(workflow["nodes"], list):
            nodes = workflow["nodes"]
            summary = []
            for node in nodes:
                ntype = node.get("type", "")
                # Skip UUID-type nodes (subgraph references)
                if len(ntype) > 50:
                    continue
                entry = {
                    "id": node.get("id"),
                    "type": ntype,
                    "title": node.get("title", ""),
                }
                # Include widget values (the actual settings)
                if node.get("widgets_values"):
                    entry["widgets_values"] = node["widgets_values"]
                summary.append(entry)

            # Cap output size
            MAX_NODES = 40
            if len(summary) > MAX_NODES:
                return json.dumps({
                    "format": "ui",
                    "node_count": len(nodes),
                    "nodes": summary[:MAX_NODES],
                    "note": f"Large workflow ({len(nodes)} nodes). Showing first {MAX_NODES}. Full workflow available at path.",
                    "path": path,
                })

            return json.dumps({
                "format": "ui",
                "node_count": len(nodes),
                "nodes": summary,
                "path": path,
            })

        # API format — return directly (already compact)
        node_count = len(workflow) if isinstance(workflow, dict) else 0
        if node_count > 40:
            # Truncate large API workflows
            trimmed = dict(list(workflow.items())[:40])
            return json.dumps({
                "format": "api",
                "node_count": node_count,
                "workflow": trimmed,
                "note": f"Showing first 40 of {node_count} nodes.",
                "path": path,
            })

        return json.dumps({
            "format": "api",
            "node_count": node_count,
            "workflow": workflow,
            "path": path,
        })

    return ToolDefinition(
        name="get_workflow_template",
        description="Load a specific workflow file as a reference template. Use search_workflows() first to find the path. Returns node types, settings, and structure that you can adapt for the user's current request.",
        parameters=[
            ToolParameter(name="path", type="string",
                          description="Full file path to the workflow .json file (from search_workflows results).",
                          required=True),
        ],
        handler=handler,
    )


# ---------------------------------------------------------------------------
# Tool: queue_prompt (execute the current workflow)
# ---------------------------------------------------------------------------

def _make_queue_prompt() -> ToolDefinition:
    async def handler() -> str:
        if not _current_workflow:
            return json.dumps({"error": "No workflow loaded. Cannot queue an empty prompt."})

        from ..providers import ComfyUIClient
        client = ComfyUIClient()

        result = await client.queue_prompt(_current_workflow)
        if not result:
            return json.dumps({
                "error": "Failed to queue prompt. Is ComfyUI running?",
                "tip": "Check that ComfyUI is reachable at http://127.0.0.1:8188",
            })

        prompt_id = result.get("prompt_id", "unknown")
        queue_remaining = result.get("number", 0)
        return json.dumps({
            "success": True,
            "prompt_id": prompt_id,
            "queue_position": queue_remaining,
            "note": "Workflow queued for execution. Use get_execution_errors() after it finishes to check for errors.",
        })

    return ToolDefinition(
        name="queue_prompt",
        description="Queue the current workflow for execution in ComfyUI. Use this after building or modifying a workflow to test if it runs successfully. Check results with get_execution_errors() afterward.",
        parameters=[],
        handler=handler,
    )


# ---------------------------------------------------------------------------
# Tool: get_execution_errors (check last execution result)
# ---------------------------------------------------------------------------

def _make_get_execution_errors() -> ToolDefinition:
    async def handler(limit: int = 1) -> str:
        from ..providers import ComfyUIClient
        client = ComfyUIClient()

        history = await client.get_history()
        if not history:
            return json.dumps({
                "error": "Could not fetch execution history. Is ComfyUI running?",
            })

        # History is {prompt_id: {status, outputs, ...}}
        # Get the most recent entries
        entries = sorted(
            history.items(),
            key=lambda x: x[1].get("status", {}).get("status_str", ""),
            reverse=True,
        )[:min(limit, 5)]

        if not entries:
            return json.dumps({"message": "No execution history found."})

        results = []
        for prompt_id, entry in entries:
            status = entry.get("status", {})
            status_str = status.get("status_str", "unknown")
            messages = status.get("messages", [])

            result_entry = {
                "prompt_id": prompt_id,
                "status": status_str,
            }

            # Check for errors in status messages
            errors = []
            for msg in messages:
                if isinstance(msg, (list, tuple)) and len(msg) >= 2:
                    msg_type = msg[0]
                    msg_data = msg[1] if isinstance(msg[1], dict) else {}
                    if "error" in str(msg_type).lower() or msg_data.get("exception_message"):
                        errors.append({
                            "type": msg_type,
                            "message": msg_data.get("exception_message", ""),
                            "details": msg_data.get("exception_type", ""),
                            "node_id": msg_data.get("node_id", ""),
                            "node_type": msg_data.get("node_type", ""),
                        })

            if errors:
                result_entry["errors"] = errors
            else:
                result_entry["message"] = "Execution completed successfully" if status_str == "success" else f"Status: {status_str}"

            results.append(result_entry)

        return json.dumps({"executions": results})

    return ToolDefinition(
        name="get_execution_errors",
        description="Check the result of the last workflow execution(s). Returns success/failure status and any error messages including node IDs and exception details. Use this after queue_prompt() to diagnose failures.",
        parameters=[
            ToolParameter(name="limit", type="integer",
                          description="Number of recent executions to check (default 1, max 5).",
                          required=False),
        ],
        handler=handler,
    )
