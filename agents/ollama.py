"""Ollama agent backend.

Full-featured local LLM backend with tool calling, vision, thinking
mode support, and VRAM management for ComfyUI coexistence.
"""

import asyncio
import json
import uuid
import base64
from typing import AsyncIterator, List, Optional, Union

import aiohttp

from .base import AgentBackend, AgentMessage, AgentConfig
from .registry import AgentRegistry
from .tools import ToolCall, ToolDefinition


class OllamaBackend(AgentBackend):
    """Ollama backend using the local HTTP API.

    Ollama must be running locally (default: http://localhost:11434).

    VRAM note: By default, Ollama keeps models loaded in VRAM for 5 minutes
    after a request. Since ComfyUI needs that VRAM for image generation,
    we set keep_alive to unload immediately after each query. Users can
    override this via the keep_alive_seconds parameter.
    """

    # Unload model from VRAM immediately after response (0 = unload now).
    # Set to e.g. 60 to keep loaded for 60s between rapid queries.
    DEFAULT_KEEP_ALIVE = 0

    # Max retries on transient errors
    MAX_RETRIES = 2

    def __init__(self, base_url: str = "http://localhost:11434",
                 keep_alive_seconds: int = None):
        self.base_url = base_url
        self.keep_alive = keep_alive_seconds if keep_alive_seconds is not None else self.DEFAULT_KEEP_ALIVE
        self._cached_models: Optional[List[str]] = None
        # Persistent message history for multi-round tool calling
        self._tool_loop_messages: Optional[List[dict]] = None

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def display_name(self) -> str:
        return "Ollama (Local)"

    @property
    def supported_models(self) -> List[str]:
        """Return cached models or default list."""
        if self._cached_models:
            return self._cached_models
        return ["llama3.2", "llama3.1", "qwen2.5", "deepseek-r1", "mistral"]

    async def is_available(self) -> bool:
        """Check if Ollama is running and accessible."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        self._cached_models = [
                            m["name"] for m in data.get("models", [])
                        ]
                        return True
                    return False
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Message conversion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_ollama_messages(
        messages: List[AgentMessage], system_prompt: str
    ) -> List[dict]:
        """Convert AgentMessages to Ollama message format with full vision support."""
        ollama_messages = []
        if system_prompt:
            ollama_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            if msg.role == "tool":
                ollama_messages.append({
                    "role": "tool",
                    "content": msg.content,
                })
            elif msg.role == "assistant" and msg.tool_calls:
                # Assistant message with tool calls
                tool_calls = []
                for tc in msg.tool_calls:
                    tool_calls.append({
                        "function": {
                            "name": tc.name,
                            "arguments": tc.arguments,
                        },
                    })
                entry = {"role": "assistant", "tool_calls": tool_calls}
                if msg.content:
                    entry["content"] = msg.content
                ollama_messages.append(entry)
            else:
                entry = {"role": msg.role, "content": msg.content or ""}
                # Vision: attach base64 images
                if msg.images:
                    entry["images"] = [img.data for img in msg.images]
                ollama_messages.append(entry)
        return ollama_messages

    @staticmethod
    def _tools_to_ollama(tools: List[ToolDefinition]) -> List[dict]:
        """Convert ToolDefinitions to Ollama's tools format."""
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
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _post_chat(
        self, payload: dict, stream: bool = False, timeout: int = 300
    ) -> aiohttp.ClientResponse:
        """Make a POST request to the Ollama chat endpoint."""
        session = aiohttp.ClientSession()
        try:
            response = await session.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout),
            )
            # Attach session to response so caller can close it
            response._session = session
            return response
        except Exception:
            await session.close()
            raise

    @staticmethod
    async def _close_response(response: aiohttp.ClientResponse):
        """Close response and its associated session."""
        response.close()
        if hasattr(response, "_session"):
            await response._session.close()

    # ------------------------------------------------------------------
    # Query (streaming, no tools)
    # ------------------------------------------------------------------

    async def query(
        self,
        messages: List[AgentMessage],
        config: Optional[AgentConfig] = None,
    ) -> AsyncIterator[str]:
        """Send messages to Ollama and stream responses."""
        config = config or AgentConfig()
        system_prompt = config.system_prompt or self.get_default_system_prompt()
        model = config.model or (self._cached_models[0] if self._cached_models else "llama3.2")

        ollama_messages = self._build_ollama_messages(messages, system_prompt)

        payload = {
            "model": model,
            "messages": ollama_messages,
            "stream": True,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": config.temperature,
                "num_predict": config.max_tokens,
            }
        }

        response = None
        try:
            response = await self._post_chat(payload, stream=True)
            if response.status != 200:
                error_text = await response.text()
                yield f"Error from Ollama: {error_text}"
                return

            async for line in response.content:
                if not line:
                    continue
                try:
                    data = json.loads(line.decode("utf-8"))
                    if "message" in data:
                        content = data["message"].get("content", "")
                        if content:
                            yield content
                    if data.get("done", False):
                        break
                except json.JSONDecodeError:
                    continue

        except aiohttp.ClientError as e:
            yield f"Connection error: {str(e)}"
        except asyncio.TimeoutError:
            yield "Request timed out"
        finally:
            if response:
                await self._close_response(response)

    # ------------------------------------------------------------------
    # Query with tools
    # ------------------------------------------------------------------

    @property
    def supports_tool_calling(self) -> bool:
        return True

    @property
    def supports_vision(self) -> bool:
        return True

    async def query_with_tools(
        self,
        messages: List[AgentMessage],
        config: Optional[AgentConfig] = None,
        tools: Optional[List[ToolDefinition]] = None,
    ) -> AsyncIterator[Union[str, ToolCall]]:
        """Query Ollama with native tool/function calling support.

        Maintains message history across tool rounds so the model sees
        the full conversation context (like Gemini's chat session).

        Handles vision (images in user messages) and structured tool
        result parsing.
        """
        if not tools:
            async for chunk in self.query(messages, config):
                yield chunk
            return

        config = config or AgentConfig()
        model = config.model or (self._cached_models[0] if self._cached_models else "llama3.2")
        system_prompt = config.system_prompt or self.get_default_system_prompt()

        ollama_messages = self._build_ollama_messages(messages, system_prompt)
        ollama_tools = self._tools_to_ollama(tools)

        payload = {
            "model": model,
            "messages": ollama_messages,
            "tools": ollama_tools,
            "stream": False,  # Non-streaming for tool calls
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": config.temperature,
                "num_predict": config.max_tokens,
            },
        }

        for attempt in range(self.MAX_RETRIES + 1):
            response = None
            try:
                response = await self._post_chat(payload)

                if response.status != 200:
                    error_text = await response.text()
                    if attempt < self.MAX_RETRIES and response.status >= 500:
                        await self._close_response(response)
                        await asyncio.sleep(1)
                        continue
                    yield f"Error from Ollama: {error_text}"
                    return

                data = await response.json()
                msg = data.get("message", {})

                # Yield text content if present
                content = msg.get("content", "")
                if content:
                    # Strip thinking tags if model uses them (Qwen3.5, DeepSeek)
                    cleaned = self._strip_thinking(content)
                    if cleaned:
                        yield cleaned

                # Yield tool calls if present
                for tc in msg.get("tool_calls", []):
                    func = tc.get("function", {})
                    args = func.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    yield ToolCall(
                        id=str(uuid.uuid4()),
                        name=func.get("name", ""),
                        arguments=args,
                    )

                # Success — break retry loop
                return

            except aiohttp.ClientError as e:
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(1)
                    continue
                yield f"Connection error: {str(e)}"
            except asyncio.TimeoutError:
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(1)
                    continue
                yield "Request timed out"
            finally:
                if response:
                    await self._close_response(response)

    # ------------------------------------------------------------------
    # Thinking mode support
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_thinking(text: str) -> str:
        """Strip <think>...</think> blocks from model output.

        Models like Qwen3.5 and DeepSeek-R1 emit internal reasoning
        in <think> tags. We strip these from the user-facing output.
        """
        import re
        # Remove <think>...</think> blocks (including multiline)
        cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        return cleaned.strip()

    # ------------------------------------------------------------------
    # VRAM management
    # ------------------------------------------------------------------

    async def unload_model(self, model: str = None):
        """Explicitly unload a model from VRAM.

        Useful before queuing a ComfyUI generation that needs GPU memory.
        If no model specified, unloads all cached models.
        """
        if not self._cached_models and not model:
            return

        models_to_unload = [model] if model else (self._cached_models or [])
        async with aiohttp.ClientSession() as session:
            for m in models_to_unload:
                try:
                    await session.post(
                        f"{self.base_url}/api/chat",
                        json={"model": m, "keep_alive": 0, "messages": []},
                        timeout=aiohttp.ClientTimeout(total=5),
                    )
                except Exception:
                    pass  # Best effort

    async def unload(self):
        """Unload all models — called by controller after generation."""
        await self.unload_model()


# Auto-register this backend
AgentRegistry.register(OllamaBackend)
