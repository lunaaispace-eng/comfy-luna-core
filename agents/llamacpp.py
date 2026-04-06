"""llama.cpp Python backend.

Uses the llama-cpp-python bindings directly — no separate server,
no Ollama, no duplication. Loads GGUF models from ComfyUI's
models/LLM/ folder using the same Python environment.

Optimized for Qwen 3.5 models with:
- Thinking mode control (disable for tool calling, enable for reasoning)
- Optimal inference settings per task type (Unsloth recommendations)
- Vision via mmproj projector files
- Multi-model support (switch between sizes for different tasks)

Usage:
    1. Place GGUF models in ComfyUI/models/LLM/
    2. Select "llama.cpp" backend in Luna Core
    3. Pick a model from the dropdown — loaded on first query

Requires: pip install llama-cpp-python
"""

import asyncio
import json
import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import AsyncIterator, List, Optional, Union

from .base import AgentBackend, AgentMessage, AgentConfig
from .registry import AgentRegistry
from .tools import ToolCall, ToolDefinition

logger = logging.getLogger("comfy-luna-core.llamacpp")

# Thread pool for blocking llama.cpp calls
_executor = ThreadPoolExecutor(max_workers=1)

# Default generation params
DEFAULT_CTX = 32768
DEFAULT_GPU_LAYERS = -1  # -1 = all layers on GPU

# Qwen 3.5 optimal inference settings (from Unsloth docs)
# Tool calling / precise tasks: low temp, no presence penalty
TOOL_CALLING_PARAMS = {
    "temperature": 0.6,
    "top_p": 0.95,
    "top_k": 20,
    "min_p": 0.0,
    "repeat_penalty": 1.0,
}

# General chat / creative tasks: higher temp, presence penalty for variety
CHAT_PARAMS = {
    "temperature": 0.7,
    "top_p": 0.8,
    "top_k": 20,
    "min_p": 0.0,
    "repeat_penalty": 1.5,
}

# Reasoning tasks: high temp, high presence penalty
REASONING_PARAMS = {
    "temperature": 1.0,
    "top_p": 0.95,
    "top_k": 20,
    "min_p": 0.0,
    "repeat_penalty": 1.5,
}


class LlamaCppBackend(AgentBackend):
    """llama.cpp Python backend — direct GGUF model loading.

    Loads models in-process via llama-cpp-python. Scans ComfyUI's
    models/LLM/ folder for available GGUF files.

    Qwen 3.5 optimized:
    - Thinking mode disabled for tool calling (faster, fewer tokens)
    - Thinking mode enabled for complex reasoning when needed
    - Correct inference params per task type
    - Vision via mmproj auto-detection
    """

    def __init__(self):
        self._cached_models: Optional[List[str]] = None
        self._model_paths: dict = {}  # display name -> full path
        self._llm = None  # Loaded Llama model instance
        self._current_model: Optional[str] = None
        self._comfyui_root: Optional[Path] = None

    @property
    def name(self) -> str:
        return "llamacpp"

    @property
    def display_name(self) -> str:
        return "llama.cpp (Local)"

    @property
    def supported_models(self) -> List[str]:
        """Return discovered GGUF models from models/LLM/."""
        if self._cached_models:
            return self._cached_models
        self._scan_models()
        return self._cached_models or []

    @property
    def supports_tool_calling(self) -> bool:
        return True

    @property
    def supports_vision(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # Model discovery
    # ------------------------------------------------------------------

    def _get_llm_folder(self) -> Optional[Path]:
        """Find ComfyUI's models/LLM/ folder."""
        if self._comfyui_root:
            llm = self._comfyui_root / "models" / "LLM"
            if llm.exists():
                return llm

        # Auto-detect ComfyUI root — try extension path first (most reliable)
        extension_root = Path(__file__).resolve().parent.parent  # agents/ -> Comfy Pilot/
        comfyui_from_ext = extension_root.parent.parent  # custom_nodes/ -> ComfyUI/

        candidates = [
            comfyui_from_ext,
            Path.cwd(),
            Path.cwd().parent,
            Path.cwd().parent.parent,
            Path.home() / "ComfyUI",
            Path.home() / "comfy" / "ComfyUI",
            Path("/workspace/ComfyUI"),
        ]
        for candidate in candidates:
            try:
                llm = candidate / "models" / "LLM"
                if llm.exists():
                    self._comfyui_root = candidate
                    return llm
            except (OSError, PermissionError):
                continue
        return None

    def _scan_models(self):
        """Scan models/LLM/ recursively for GGUF files."""
        llm_folder = self._get_llm_folder()
        if not llm_folder:
            self._cached_models = []
            return

        models = []
        self._model_paths = {}

        for path in llm_folder.rglob("*.gguf"):
            # Skip vision projector files
            if "mmproj" in path.name.lower() or "projector" in path.name.lower():
                continue

            # Display name: relative path from LLM/
            rel = path.relative_to(llm_folder)
            display_name = str(rel).replace("\\", "/")
            models.append(display_name)
            self._model_paths[display_name] = path

        # Sort: prefer newer models, larger quantizations
        models.sort(key=lambda m: (
            "3.5" not in m.lower(),
            "3-" not in m.lower() and "3_" not in m.lower(),
            "q8" not in m.lower(),
            "q6" not in m.lower(),
            "q4" not in m.lower(),
            m.lower(),
        ))

        self._cached_models = models
        logger.info(f"Found {len(models)} GGUF models in {llm_folder}")

    def _find_mmproj(self, model_path: Path) -> Optional[str]:
        """Find a vision projector file next to the model."""
        parent = model_path.parent
        for f in parent.iterdir():
            if f.suffix == ".gguf" and (
                "mmproj" in f.name.lower() or "projector" in f.name.lower()
            ):
                return str(f)
        return None

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _load_model(self, model_name: str) -> bool:
        """Load a GGUF model into memory. Runs in thread pool."""
        if self._current_model == model_name and self._llm is not None:
            return True

        # Unload current model first
        self._unload_model()

        model_path = self._model_paths.get(model_name)
        if not model_path or not model_path.exists():
            logger.error(f"Model file not found: {model_name}")
            return False

        try:
            from llama_cpp import Llama

            # Check for vision projector
            mmproj = self._find_mmproj(model_path)

            kwargs = {
                "model_path": str(model_path),
                "n_ctx": DEFAULT_CTX,
                "n_gpu_layers": DEFAULT_GPU_LAYERS,
                "flash_attn": True,
                "verbose": False,
                # Qwen 3.5: disable thinking mode for tool calling efficiency
                "chat_template_kwargs": {"enable_thinking": False},
            }

            # Add chat handler for vision models
            if mmproj:
                try:
                    from llama_cpp.llama_chat_format import Llava16ChatHandler
                    kwargs["chat_handler"] = Llava16ChatHandler(
                        clip_model_path=mmproj
                    )
                    logger.info(f"Vision projector loaded: {Path(mmproj).name}")
                except ImportError:
                    logger.warning("llava chat handler not available, vision disabled")

            logger.info(
                f"Loading model: {model_name} "
                f"(ctx={DEFAULT_CTX}, gpu_layers={DEFAULT_GPU_LAYERS}, thinking=off)"
            )
            self._llm = Llama(**kwargs)
            self._current_model = model_name
            logger.info(f"Model loaded: {model_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to load model {model_name}: {e}")
            self._llm = None
            self._current_model = None
            return False

    def _unload_model(self):
        """Unload the current model to free VRAM."""
        if self._llm is not None:
            del self._llm
            self._llm = None
            self._current_model = None
            import gc
            gc.collect()
            logger.info("Model unloaded")

    async def _ensure_model(self, model_name: str) -> bool:
        """Ensure the model is loaded (async wrapper)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, self._load_model, model_name)

    # ------------------------------------------------------------------
    # Availability check
    # ------------------------------------------------------------------

    async def is_available(self) -> bool:
        """Check if llama-cpp-python is installed and models exist."""
        try:
            import llama_cpp  # noqa: F401
        except ImportError:
            return False

        self._scan_models()
        return bool(self._cached_models)

    # ------------------------------------------------------------------
    # Message building
    # ------------------------------------------------------------------

    @staticmethod
    def _build_messages(
        messages: List[AgentMessage], system_prompt: str
    ) -> List[dict]:
        """Convert AgentMessages to llama-cpp-python chat format."""
        chat_messages = []
        if system_prompt:
            chat_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            if msg.role == "tool":
                chat_messages.append({
                    "role": "tool",
                    "content": msg.content,
                    "tool_call_id": msg.tool_call_id or "",
                })
            elif msg.role == "assistant" and msg.tool_calls:
                tool_calls = []
                for tc in msg.tool_calls:
                    tool_calls.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments)
                            if isinstance(tc.arguments, dict) else tc.arguments,
                        },
                    })
                entry = {"role": "assistant", "tool_calls": tool_calls}
                if msg.content:
                    entry["content"] = msg.content
                chat_messages.append(entry)
            else:
                # User or plain assistant message
                if msg.images:
                    # Vision: multimodal content with base64 images
                    content = [{"type": "text", "text": msg.content or ""}]
                    for img in msg.images:
                        content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{img.media_type};base64,{img.data}"
                            },
                        })
                    chat_messages.append({"role": msg.role, "content": content})
                else:
                    chat_messages.append({
                        "role": msg.role,
                        "content": msg.content or "",
                    })

        return chat_messages

    @staticmethod
    def _tools_to_openai(tools: List[ToolDefinition]) -> List[dict]:
        """Convert ToolDefinitions to OpenAI function calling format."""
        result = []
        for tool in tools:
            properties = {}
            required = []
            for param in tool.parameters:
                desc = param.description
                if param.default is not None:
                    desc += f" (default: {param.default})"
                prop = {"type": param.type, "description": desc}
                if param.enum:
                    prop["enum"] = param.enum
                properties[param.name] = prop
                if param.required:
                    required.append(param.name)
            result.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            })
        return result

    # ------------------------------------------------------------------
    # Thinking mode support
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_thinking(text: str) -> str:
        """Strip <think>...</think> blocks from model output.

        Even with thinking disabled, some models may emit partial
        thinking tags. Clean them to ensure user sees only the response.
        """
        cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        return cleaned.strip()

    # ------------------------------------------------------------------
    # Query (streaming, no tools)
    # ------------------------------------------------------------------

    async def query(
        self,
        messages: List[AgentMessage],
        config: Optional[AgentConfig] = None,
    ) -> AsyncIterator[str]:
        """Send messages and stream text responses.

        Uses CHAT_PARAMS by default (creative, anti-repetition).
        """
        config = config or AgentConfig()
        model_name = config.model or (
            self._cached_models[0] if self._cached_models else None
        )

        if not model_name:
            yield "No GGUF models found in models/LLM/ folder."
            return

        if not await self._ensure_model(model_name):
            yield f"Failed to load {model_name}. Check logs."
            return

        system_prompt = config.system_prompt or self.get_default_system_prompt()
        chat_messages = self._build_messages(messages, system_prompt)

        # Use chat params for general conversation
        params = dict(CHAT_PARAMS)

        try:
            loop = asyncio.get_event_loop()

            def _generate():
                return self._llm.create_chat_completion(
                    messages=chat_messages,
                    max_tokens=config.max_tokens,
                    stream=True,
                    **params,
                )

            stream = await loop.run_in_executor(_executor, _generate)

            for chunk in stream:
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    cleaned = self._strip_thinking(content)
                    if cleaned:
                        yield cleaned
                await asyncio.sleep(0)

        except Exception as e:
            logger.error(f"Generation error: {e}")
            yield f"Error: {str(e)}"

    # ------------------------------------------------------------------
    # Query with tools
    # ------------------------------------------------------------------

    async def query_with_tools(
        self,
        messages: List[AgentMessage],
        config: Optional[AgentConfig] = None,
        tools: Optional[List[ToolDefinition]] = None,
    ) -> AsyncIterator[Union[str, ToolCall]]:
        """Query with function calling support.

        Uses TOOL_CALLING_PARAMS (temp=0.6, precise, no presence penalty)
        as recommended by Unsloth for Qwen 3.5 tool calling.
        """
        if not tools:
            async for chunk in self.query(messages, config):
                yield chunk
            return

        config = config or AgentConfig()
        model_name = config.model or (
            self._cached_models[0] if self._cached_models else None
        )

        if not model_name:
            yield "No GGUF models found in models/LLM/ folder."
            return

        if not await self._ensure_model(model_name):
            yield f"Failed to load {model_name}. Check logs."
            return

        system_prompt = config.system_prompt or self.get_default_system_prompt()
        chat_messages = self._build_messages(messages, system_prompt)
        oai_tools = self._tools_to_openai(tools)

        # Use tool calling params (precise, low temperature)
        params = dict(TOOL_CALLING_PARAMS)

        try:
            loop = asyncio.get_event_loop()

            def _generate():
                return self._llm.create_chat_completion(
                    messages=chat_messages,
                    tools=oai_tools,
                    tool_choice="auto",
                    max_tokens=config.max_tokens,
                    stream=False,
                    **params,
                )

            result = await loop.run_in_executor(_executor, _generate)

            choice = result.get("choices", [{}])[0]
            msg = choice.get("message", {})

            # Yield text content
            content = msg.get("content", "")
            if content:
                cleaned = self._strip_thinking(content)
                if cleaned:
                    yield cleaned

            # Yield tool calls
            for tc in msg.get("tool_calls", []):
                func = tc.get("function", {})
                args = func.get("arguments", "{}")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                yield ToolCall(
                    id=tc.get("id", str(uuid.uuid4())),
                    name=func.get("name", ""),
                    arguments=args,
                )

        except Exception as e:
            logger.error(f"Generation error: {e}")
            yield f"Error: {str(e)}"

    # ------------------------------------------------------------------
    # VRAM management
    # ------------------------------------------------------------------

    async def unload(self):
        """Unload model to free VRAM for ComfyUI."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_executor, self._unload_model)

    def __del__(self):
        """Clean up on destruction."""
        self._unload_model()


# Auto-register this backend
AgentRegistry.register(LlamaCppBackend)
