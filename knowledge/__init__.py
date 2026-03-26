"""ComfyUI knowledge base for agents.

Uses markdown files with YAML frontmatter for knowledge.
Auto-generates node and model knowledge from the actual ComfyUI installation.
User can drop custom .md files in knowledge/user/ for additional context.
"""

from .manager import KnowledgeManager, KnowledgeFile

__all__ = [
    "KnowledgeManager",
    "KnowledgeFile",
]
