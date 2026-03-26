"""Google Gemini agent backend.

Uses the google-genai SDK to communicate with Gemini models via the
Gemini API.  Tool calling uses the SDK's chat session which handles
thought_signatures automatically.
"""

import asyncio
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncIterator, List, Optional, Union

from .base import AgentBackend, AgentMessage, AgentConfig
from .registry import AgentRegistry
from .tools import ToolCall, ToolDefinition

# Thread pool for sync SDK calls (google-genai is synchronous)
_executor = ThreadPoolExecutor(max_workers=3)


class GeminiBackend(AgentBackend):
    """Google Gemini API backend.

    Requires:
        - google-genai package installed (pip install google-genai)
        - GEMINI_API_KEY or GOOGLE_API_KEY environment variable set

    Supports Gemini 2.5/3.x Pro, Flash, and other Gemini models
    with native function calling via the SDK's chat session
    (automatically handles thought_signatures).
    """

    # Fallback if API model listing fails
    _DEFAULT_MODELS = [
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
    ]

    # Skip models that can't do generateContent chat
    _SKIP_KEYWORDS = (
        "tts", "embedding", "image-generation", "audio",
        "compute", "computer", "robotics", "search",
        "imagen", "veo",
    )

    def __init__(self):
        self._client = None
        self._cached_models: Optional[List[str]] = None
        # Persistent chat session for multi-round tool calling within one user turn
        self._active_chat = None
        self._pending_tool_calls: List[ToolCall] = []

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def display_name(self) -> str:
        return "Google Gemini"

    @property
    def supported_models(self) -> List[str]:
        """Return dynamically fetched models, or defaults if not yet fetched."""
        if self._cached_models:
            return self._cached_models
        return self._DEFAULT_MODELS

    def _get_api_key(self) -> Optional[str]:
        return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    def _ensure_client(self):
        """Lazily initialize the google-genai client."""
        if self._client is not None:
            return
        from google import genai
        api_key = self._get_api_key()
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY or GOOGLE_API_KEY environment variable not set"
            )
        self._client = genai.Client(api_key=api_key)

    async def is_available(self) -> bool:
        """Check if the Gemini API is accessible and fetch available models."""
        if not self._get_api_key():
            return False
        try:
            from google import genai  # noqa: F401
        except ImportError:
            return False
        try:
            self._ensure_client()
            import re
            # Fetch available Gemini models from the API
            models = []
            for model in self._client.models.list():
                model_id = getattr(model, "name", "") or ""
                # API returns "models/gemini-2.5-pro" format
                short_name = model_id.replace("models/", "") if model_id.startswith("models/") else model_id

                # Only include gemini chat models
                if not short_name.startswith("gemini-"):
                    continue

                # Check supported methods if available
                methods = getattr(model, "supported_generation_methods", None)
                if methods and "generateContent" not in methods:
                    continue

                # Skip non-chat models by keyword
                if any(kw in short_name for kw in self._SKIP_KEYWORDS):
                    continue

                # Skip versioned/dated variants (e.g. gemini-2.5-pro-preview-05-06)
                if re.search(r'-\d{2,4}-\d{2}', short_name):
                    continue
                # Skip -preview-NNN, -exp-NNNN, -latest variants
                if re.search(r'-(preview|exp|latest)-?\d', short_name):
                    continue
                # Skip -001, -002 suffixed variants
                if re.search(r'-\d{3}$', short_name):
                    continue

                models.append(short_name)

            # Deduplicate
            models = list(dict.fromkeys(models))

            if models:
                # Sort: prefer 2.5 > 2.0, pro > flash > lite
                models.sort(key=lambda m: (
                    "2.5" not in m,
                    "2.0" not in m,
                    "pro" not in m,
                    "lite" in m,
                    m,
                ))
                self._cached_models = models
                return True
            # API worked but no models found — fall back to defaults
            self._cached_models = list(self._DEFAULT_MODELS)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Message conversion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_contents(messages: List[AgentMessage]) -> list:
        """Convert AgentMessages into Gemini content dicts.

        Only converts user and plain assistant messages (no tool_calls).
        Tool-calling turns are handled by the chat session automatically.
        """
        from google.genai import types

        contents = []
        for msg in messages:
            if msg.role == "user":
                parts = [types.Part(text=msg.content)]
                if msg.images:
                    import base64
                    for img in msg.images:
                        parts.append(types.Part(
                            inline_data=types.Blob(
                                mime_type=img.media_type,
                                data=base64.b64decode(img.data),
                            )
                        ))
                contents.append(types.Content(
                    role="user",
                    parts=parts,
                ))
            elif msg.role == "assistant":
                # Only include plain text assistant messages as history.
                # Tool-calling assistant messages are handled by the chat session.
                if not msg.tool_calls and msg.content:
                    contents.append(types.Content(
                        role="model",
                        parts=[types.Part(text=msg.content)],
                    ))
            # Skip tool messages — they're handled by the chat session
            # Skip system messages — handled via system_instruction

        return contents

    @staticmethod
    def _tools_to_gemini(tools: List[ToolDefinition]) -> list:
        """Convert ToolDefinitions into Gemini function declarations."""
        from google.genai import types

        declarations = []
        for tool in tools:
            properties = {}
            required = []
            for param in tool.parameters:
                prop = types.Schema(
                    type=param.type.upper(),
                    description=param.description,
                )
                if param.enum:
                    prop = types.Schema(
                        type=param.type.upper(),
                        description=param.description,
                        enum=param.enum,
                    )
                properties[param.name] = prop
                if param.required:
                    required.append(param.name)

            declarations.append(types.FunctionDeclaration(
                name=tool.name,
                description=tool.description,
                parameters=types.Schema(
                    type="OBJECT",
                    properties=properties,
                    required=required if required else None,
                ),
            ))

        return [types.Tool(function_declarations=declarations)]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _reset_chat_session(self):
        """Reset the chat session state between user turns."""
        self._active_chat = None
        self._pending_tool_calls = []

    def _run_sync(self, fn, *args):
        """Run a synchronous SDK call in a thread pool to avoid blocking the event loop."""
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(_executor, fn, *args)

    # ------------------------------------------------------------------
    # Query (streaming, no tools)
    # ------------------------------------------------------------------

    async def query(
        self,
        messages: List[AgentMessage],
        config: Optional[AgentConfig] = None,
    ) -> AsyncIterator[str]:
        """Send messages to Gemini and stream text responses."""
        config = config or AgentConfig()
        self._ensure_client()
        self._reset_chat_session()

        from google.genai import types

        model = config.model or "gemini-2.5-flash"
        system_prompt = config.system_prompt or self.get_default_system_prompt()

        contents = self._build_contents(messages)

        gen_config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=config.temperature,
            max_output_tokens=config.max_tokens,
        )

        try:
            response = self._client.models.generate_content_stream(
                model=model,
                contents=contents,
                config=gen_config,
            )
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            yield f"Error from Gemini: {e}"

    # ------------------------------------------------------------------
    # Query with tools (using SDK chat session for thought_signature)
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
        """Query Gemini with native function calling support.

        Uses the SDK's chat session which automatically handles
        thought_signatures for thinking models (Gemini 2.5+, 3.x).

        Flow:
        1. First call in a tool loop: creates a new chat session, sends
           the user message, may receive function_call parts back.
        2. Subsequent calls (tool results): sends FunctionResponse parts
           via the same chat session — the SDK manages thought_signatures.
        3. When the model returns only text (no more function calls),
           the chat session is released.
        """
        if not tools:
            async for chunk in self.query(messages, config):
                yield chunk
            return

        config = config or AgentConfig()
        self._ensure_client()

        from google.genai import types

        model = config.model or "gemini-2.5-flash"
        system_prompt = config.system_prompt or self.get_default_system_prompt()

        gemini_tools = self._tools_to_gemini(tools)

        gen_config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=config.temperature,
            max_output_tokens=config.max_tokens,
            tools=gemini_tools,
        )

        try:
            # Detect if this is a continuation (tool results from previous round)
            is_continuation = (
                self._active_chat is not None
                and self._pending_tool_calls
                and len(messages) >= 2
                and messages[-1].role == "tool"
            )

            if is_continuation:
                # Build FunctionResponse parts for each pending tool result
                function_responses = []
                # Collect only the trailing tool messages (this round's results)
                for msg in reversed(messages):
                    if msg.role != "tool":
                        break
                    if msg.tool_call_id:
                        # Find the matching tool call name
                        tc_name = None
                        if msg.metadata and "tool_name" in msg.metadata:
                            tc_name = msg.metadata["tool_name"]
                        else:
                            for tc in self._pending_tool_calls:
                                if tc.id == msg.tool_call_id:
                                    tc_name = tc.name
                                    break
                        if tc_name:
                            function_responses.append(types.Part(
                                function_response=types.FunctionResponse(
                                    name=tc_name,
                                    response={"result": msg.content},
                                )
                            ))

                # Reverse back to original order (we iterated in reverse)
                function_responses.reverse()
                self._pending_tool_calls = []

                if not function_responses:
                    # No matching tool results — abandon chat, start fresh
                    self._active_chat = None
                else:
                    # Send tool results via existing chat session
                    response = await self._run_sync(
                        self._active_chat.send_message, function_responses
                    )

                    new_tool_calls = []
                    if response.candidates:
                        content = response.candidates[0].content
                        parts = content.parts if content else None
                        for part in (parts or []):
                            if part.text:
                                yield part.text
                            elif part.function_call:
                                fc = part.function_call
                                args = dict(fc.args) if fc.args else {}
                                tc = ToolCall(
                                    id=str(uuid.uuid4()),
                                    name=fc.name,
                                    arguments=args,
                                )
                                new_tool_calls.append(tc)
                                yield tc

                    if new_tool_calls:
                        self._pending_tool_calls = new_tool_calls
                    else:
                        # No more tool calls — conversation round complete
                        self._active_chat = None
                    return

            # --- First call or fresh start ---
            self._active_chat = None
            self._pending_tool_calls = []

            # Build history from prior messages (excluding the last user message)
            history = self._build_contents(messages[:-1]) if len(messages) > 1 else []

            # Extract the last user message
            last_msg = messages[-1] if messages else None
            if not last_msg:
                return

            last_parts = [types.Part(text=last_msg.content)]
            if last_msg.images:
                import base64
                for img in last_msg.images:
                    last_parts.append(types.Part(
                        inline_data=types.Blob(
                            mime_type=img.media_type,
                            data=base64.b64decode(img.data),
                        )
                    ))

            # Create a new chat session
            chat = self._client.chats.create(
                model=model,
                config=gen_config,
                history=history,
            )

            # Send the user message (run in thread pool to not block event loop)
            response = await self._run_sync(chat.send_message, last_parts)

            # Process response parts
            new_tool_calls = []
            if response.candidates:
                content = response.candidates[0].content
                parts = content.parts if content else None
                for part in (parts or []):
                    if part.text:
                        yield part.text
                    elif part.function_call:
                        fc = part.function_call
                        args = dict(fc.args) if fc.args else {}
                        tc = ToolCall(
                            id=str(uuid.uuid4()),
                            name=fc.name,
                            arguments=args,
                        )
                        new_tool_calls.append(tc)
                        yield tc

            if new_tool_calls:
                # Keep the chat session alive for the next round
                self._active_chat = chat
                self._pending_tool_calls = new_tool_calls
            else:
                self._active_chat = None

        except Exception as e:
            self._reset_chat_session()
            yield f"Error from Gemini: {e}"


# Auto-register this backend
AgentRegistry.register(GeminiBackend)
