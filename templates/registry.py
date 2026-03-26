"""Workflow registry — indexes local user workflows and official templates.

Scans workflow directories, extracts metadata (node types, model family,
name), and provides fuzzy search so the agent can find and adapt proven
workflows instead of inventing from memory.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("luna_core.templates")


@dataclass
class WorkflowEntry:
    """A single indexed workflow."""

    name: str  # Display name (from filename)
    path: str  # Absolute path to the .json file
    category: str  # Folder name (e.g., "FLUX", "SDXL", "WAN")
    source: str  # "local" or "official"
    node_types: List[str] = field(default_factory=list)
    node_count: int = 0
    file_size: int = 0


class WorkflowRegistry:
    """Indexes and searches workflow files from configured sources.

    Sources are discovered automatically:
    - Local user workflows: {comfyui_root}/user/default/workflows/
    - Official templates: bundled in templates/official/ (if synced)
    """

    def __init__(self):
        self._entries: List[WorkflowEntry] = []
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def count(self) -> int:
        return len(self._entries)

    def load(self, sources: Optional[List[Dict[str, str]]] = None) -> int:
        """Scan workflow sources and build the index.

        Args:
            sources: List of {"path": ..., "type": "local"|"official"} dicts.
                     If None, auto-discovers from ComfyUI installation.

        Returns:
            Number of workflows indexed.
        """
        self._entries.clear()

        if sources is None:
            sources = self._auto_discover_sources()

        for source in sources:
            src_path = Path(source["path"])
            src_type = source.get("type", "local")
            if not src_path.exists():
                logger.debug("Workflow source not found: %s", src_path)
                continue
            self._scan_directory(src_path, src_type)

        self._loaded = True
        logger.info("Workflow registry: indexed %d workflows from %d sources",
                     len(self._entries), len(sources))
        return len(self._entries)

    def _auto_discover_sources(self) -> List[Dict[str, str]]:
        """Find workflow directories from the ComfyUI installation."""
        sources = []

        # Find ComfyUI root from extension path
        # Extension is at: ComfyUI/custom_nodes/comfy-luna-core/templates/registry.py
        extension_root = Path(__file__).parent.parent  # comfy-luna-core/
        comfyui_root = extension_root.parent.parent  # ComfyUI/

        candidates = [comfyui_root, Path.cwd(), Path.cwd().parent]

        for candidate in candidates:
            user_workflows = candidate / "user" / "default" / "workflows"
            if user_workflows.exists():
                sources.append({"path": str(user_workflows), "type": "local"})
                logger.info("Found local workflows: %s", user_workflows)
                break

        # Check for official templates bundled with extension
        official_dir = Path(__file__).parent / "official"
        if official_dir.exists():
            sources.append({"path": str(official_dir), "type": "official"})

        return sources

    def _scan_directory(self, directory: Path, source_type: str, category: str = "") -> None:
        """Recursively scan a directory for .json workflow files."""
        try:
            for entry in sorted(directory.iterdir()):
                if entry.is_dir():
                    # Use folder name as category
                    sub_category = entry.name
                    self._scan_directory(entry, source_type, sub_category)
                elif entry.suffix.lower() == ".json" and entry.stat().st_size > 100:
                    self._index_workflow(entry, source_type, category)
        except PermissionError:
            logger.debug("Permission denied scanning: %s", directory)

    def _index_workflow(self, path: Path, source_type: str, category: str) -> None:
        """Parse a workflow file and extract metadata for indexing."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.debug("Could not parse workflow: %s", path)
            return

        node_types = []
        node_count = 0

        # UI format (LiteGraph): has "nodes" array
        if isinstance(data, dict) and "nodes" in data and isinstance(data["nodes"], list):
            node_count = len(data["nodes"])
            seen = set()
            for node in data["nodes"]:
                ntype = node.get("type", "")
                if ntype and ntype not in seen:
                    # Skip UUID-style node types (custom subgraph references)
                    if len(ntype) < 60 and not _is_uuid(ntype):
                        seen.add(ntype)
                        node_types.append(ntype)

        # API format: dict with string keys, each has "class_type"
        elif isinstance(data, dict) and all(isinstance(v, dict) for v in data.values()):
            node_count = len(data)
            seen = set()
            for node_data in data.values():
                ct = node_data.get("class_type", "")
                if ct and ct not in seen:
                    seen.add(ct)
                    node_types.append(ct)

        if node_count == 0:
            return  # Not a recognizable workflow

        # Clean name from filename
        name = path.stem
        # Remove common prefixes/suffixes that are just noise
        name = name.replace("_", " ").replace("-", " ").strip()

        entry = WorkflowEntry(
            name=name,
            path=str(path),
            category=category or "uncategorized",
            source=source_type,
            node_types=sorted(node_types),
            node_count=node_count,
            file_size=path.stat().st_size,
        )
        self._entries.append(entry)

    def search(self, query: str = "", category: str = "",
               node_type: str = "", limit: int = 20) -> List[WorkflowEntry]:
        """Search indexed workflows.

        Args:
            query: Fuzzy text search against name and category.
            category: Filter by category (folder name, case-insensitive).
            node_type: Filter by node type used in workflow.
            limit: Max results.

        Returns:
            List of matching WorkflowEntry objects.
        """
        if not self._loaded:
            self.load()

        results = []
        query_lower = query.lower()
        category_lower = category.lower()
        node_type_lower = node_type.lower()

        for entry in self._entries:
            # Category filter
            if category_lower and category_lower not in entry.category.lower():
                continue

            # Node type filter
            if node_type_lower:
                if not any(node_type_lower in nt.lower() for nt in entry.node_types):
                    continue

            # Text search (name + category + node types)
            if query_lower:
                searchable = f"{entry.name} {entry.category} {' '.join(entry.node_types)}".lower()
                # All query terms must match
                terms = query_lower.split()
                if not all(term in searchable for term in terms):
                    continue

            results.append(entry)
            if len(results) >= limit:
                break

        return results

    def get_categories(self) -> List[Dict[str, Any]]:
        """Get all categories with workflow counts."""
        if not self._loaded:
            self.load()

        cats: Dict[str, int] = {}
        for entry in self._entries:
            cats[entry.category] = cats.get(entry.category, 0) + 1

        return [{"name": k, "count": v} for k, v in sorted(cats.items())]

    def get_workflow(self, path: str) -> Optional[Dict[str, Any]]:
        """Load and return the full workflow JSON from a path."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError, PermissionError) as e:
            logger.warning("Could not load workflow %s: %s", path, e)
            return None

    def to_summary(self, entries: Optional[List[WorkflowEntry]] = None) -> str:
        """Generate a text summary of workflows for agent context."""
        if entries is None:
            entries = self._entries

        if not entries:
            return "No workflows found."

        lines = [f"Found {len(entries)} workflow(s):\n"]
        for entry in entries:
            source_tag = f" [{entry.source}]" if entry.source != "local" else ""
            lines.append(
                f"- **{entry.name}** ({entry.category}{source_tag}) — "
                f"{entry.node_count} nodes"
            )
            if entry.node_types:
                # Show key node types (loaders, samplers) not every utility node
                key_types = [t for t in entry.node_types
                             if any(kw in t.lower() for kw in
                                    ("loader", "sampler", "ksampler", "wan", "flux",
                                     "controlnet", "lora", "vae", "encode", "video",
                                     "upscale", "animate", "qwen", "ltx", "hunyuan"))]
                if key_types:
                    lines.append(f"  Key nodes: {', '.join(key_types[:8])}")

        return "\n".join(lines)


def _is_uuid(s: str) -> bool:
    """Quick check if a string looks like a UUID."""
    if len(s) == 36 and s.count("-") == 4:
        try:
            parts = s.split("-")
            return len(parts) == 5 and all(len(p) in (8, 4, 4, 4, 12) for p in parts)
        except Exception:
            return False
    return False
