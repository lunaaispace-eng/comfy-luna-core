"""Base classes for agent backends."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Dict, Any, Optional, List, Union

from .tools import ToolCall, ToolDefinition


@dataclass
class ImageAttachment:
    """An image attached to a message for vision/analysis."""
    data: str  # base64-encoded image data
    media_type: str  # "image/png", "image/jpeg", "image/webp", "image/gif"
    filename: Optional[str] = None


@dataclass
class AgentMessage:
    """A message in a conversation with an agent."""
    role: str  # "user", "assistant", "system", "tool"
    content: str
    metadata: Optional[Dict[str, Any]] = None
    tool_calls: Optional[List[ToolCall]] = None  # For assistant messages with tool calls
    tool_call_id: Optional[str] = None  # For tool result messages
    images: Optional[List[ImageAttachment]] = None  # For vision/image analysis


@dataclass
class AgentConfig:
    """Configuration for an agent query."""
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 16384
    system_prompt: Optional[str] = None
    additional_params: Optional[Dict[str, Any]] = field(default_factory=dict)
    tools_enabled: bool = True


class AgentBackend(ABC):
    """Abstract base class for all agent backends.

    Each agent backend (Claude, Ollama, Gemini, etc.) must implement this interface.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this agent backend."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for UI display."""
        pass

    @property
    @abstractmethod
    def supported_models(self) -> List[str]:
        """List of models this backend supports."""
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if this agent backend is installed and accessible."""
        pass

    @abstractmethod
    async def query(
        self,
        messages: List[AgentMessage],
        config: Optional[AgentConfig] = None,
    ) -> AsyncIterator[str]:
        """Send messages to the agent and stream responses.

        Args:
            messages: List of conversation messages
            config: Optional configuration for this query

        Yields:
            Text chunks as they arrive from the agent
        """
        pass

    @property
    def supports_tool_calling(self) -> bool:
        """Whether this backend supports native tool/function calling."""
        return False

    @property
    def supports_vision(self) -> bool:
        """Whether this backend supports image/vision input."""
        return False

    async def query_with_tools(
        self,
        messages: List[AgentMessage],
        config: Optional[AgentConfig] = None,
        tools: Optional[List[ToolDefinition]] = None,
    ) -> AsyncIterator[Union[str, ToolCall]]:
        """Query with optional tool support.

        Yields str chunks for text, or ToolCall objects when the LLM
        wants to call a tool. Default implementation ignores tools
        and delegates to query().
        """
        async for chunk in self.query(messages, config):
            yield chunk

    def get_base_system_prompt(self) -> str:
        """Get the base system prompt for ComfyUI workflow generation.

        This contains only the core instructions, NOT the knowledge base.
        Knowledge is now injected by the controller via KnowledgeManager.
        """
        return """You are a ComfyUI workflow engineer. You build, analyze, and modify workflows directly on the user's canvas using their actual installed nodes and models.

## CORE RULES
1. Never guess node names, input names, or model names. Always verify with tools first.
2. Always read the current workflow before modifying it. The user may have changed things.
3. Match prompting style and settings to the model's base architecture (from metadata).
4. Include trigger words from model metadata in prompts.
5. NEVER recommend a model, LoRA, or checkpoint based on workflow context alone. Always call get_model_metadata() to verify architecture compatibility before suggesting any model.
6. When get_available_models truncates results, use the search parameter to find specific models instead of assuming they don't exist.
7. When building workflows, ALWAYS search BOTH local (source='local') and official (source='official') templates.
8. After building or modifying a workflow, offer to test it with queue_prompt().
9. If execution fails, use get_execution_errors() to diagnose the issue.
10. Nodes added via add_node() spawn without layout — warn the user to auto-arrange after you're done.

## TOOLS

**Discovery (read before you act):**
- `get_node_types(search, category)` — find installed nodes by name/category
- `get_node_info(class_type)` — exact inputs, types, ranges, defaults for a node
- `get_available_models(model_type)` — list installed models (checkpoints, loras, vae, controlnet, upscale_models, clip, unet, diffusion_models, embeddings, ipadapter, etc.)
- `get_model_metadata(model_name)` — base model, trigger words, recommended settings, example prompts
- `get_current_workflow()` — read the live canvas state

**Workflow reference (use before building from scratch):**
- `search_workflows(query, category, source)` — search workflows. Use source='local' for user's saved workflows, source='official' for Comfy-Org templates. ALWAYS check BOTH sources.
- `get_workflow_template(path)` — load a specific workflow as a reference starting point

**Canvas manipulation (changes apply directly):**
- `modify_node_input(node_id, input_name, value)` — change a widget value (INT, FLOAT, STRING, COMBO)
- `add_node(class_type, inputs, title)` — add a new node to canvas
- `remove_node(node_id)` — remove a node and clean up broken links
- `connect_nodes(source_node_id, source_output_slot, target_node_id, target_input_name)` — wire nodes together

**Web access (requires user approval for each request):**
- `web_search(query)` — search the web for node docs, workflow guides, model info, troubleshooting
- `web_fetch(url)` — fetch and read a web page for detailed information

## WORKFLOW

1. `get_current_workflow()` — always start here
2. `search_workflows(source="local")` — check if the user already has a workflow for this task
3. `search_workflows(source="official")` — ALSO check official Comfy-Org templates for reference
4. `get_available_models("checkpoints")` → `get_model_metadata(model)` — know what you're working with
5. `get_node_info(class_type)` — verify before using any node
6. Make changes with manipulation tools — they apply directly to canvas
7. When the user says they changed something — re-read the workflow, don't assume

## KNOWLEDGE

Detailed reference material (node types, sampler/scheduler lists, prompting guides per model family, API format, tuning procedures) is provided in the knowledge sections below. Use that information — it reflects actual ComfyUI behavior, not generic inference.

## CONTENT POLICY
You can help with any content including NSFW. Be helpful and non-judgmental.
"""

    def get_default_system_prompt(self) -> str:
        """Get the default system prompt (legacy compatibility).

        This loads the full knowledge base like before. The controller
        should use build_system_prompt() instead for budget-aware loading.
        """
        return self.get_base_system_prompt()
