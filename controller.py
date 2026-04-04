"""Main controller for comfy-luna-core.

Handles HTTP endpoints and coordinates agent communication,
knowledge selection, workflow validation, and auto-correction.
"""

import asyncio
import json
import logging
import uuid
from typing import Dict, Any, List, Optional, Set

from aiohttp import web

from .agents import AgentRegistry, AgentMessage, AgentConfig, ImageAttachment
from .agents.ollama import OllamaBackend  # noqa: F401 - registers itself
from .agents.tools import ToolCall, ToolRegistry
from .agents.comfyui_tools import setup_tools, set_current_workflow, get_pending_modifications
from .agents.web_tools import setup_web_tools
from .agents.planner import classify_intent, get_strategy_note
from .knowledge import KnowledgeManager
from .knowledge.auto_generator import generate_all as generate_auto_knowledge
from .providers import ComfyUIClient
from .system import SystemMonitor
from .templates import WorkflowRegistry
from .validation import NodeRegistry, WorkflowValidator
from .workflow import WorkflowManipulator

logger = logging.getLogger("comfy-luna-core")

MAX_CORRECTION_RETRIES = 3
MAX_TOOL_ROUNDS = 20  # High cap — loop-breaking logic below prevents runaway
MAX_REPEAT_TOOL_CALLS = 3  # Stop if same tool called this many times consecutively
MAX_TOOL_RESPONSE_CHARS = 8000  # ~2K tokens — prevents context exhaustion
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


class LunaCoreController:
    """Main controller handling HTTP routes and agent coordination."""

    def __init__(self):
        self.conversations: Dict[str, List[AgentMessage]] = {}
        self.knowledge_manager = KnowledgeManager()
        self.knowledge_manager.load_all()
        self.comfyui_client = ComfyUIClient()
        self.node_registry = NodeRegistry(client=self.comfyui_client)
        self.validator = WorkflowValidator(self.node_registry)
        self.workflow_registry = WorkflowRegistry()
        self._tools = setup_tools(self.node_registry, SystemMonitor, self.workflow_registry)
        # Add web tools (require user approval)
        web_tools = setup_web_tools()
        for wt in web_tools:
            ToolRegistry.register(wt)
        self._tools.extend(web_tools)
        self._auto_knowledge_generated = False
        # Pending approval requests: {approval_id: asyncio.Future}
        self._pending_approvals: Dict[str, asyncio.Future] = {}

    def setup_routes(self, routes: web.RouteTableDef) -> None:
        """Register HTTP routes with aiohttp."""

        @routes.get("/luna/agents")
        async def get_agents(request: web.Request) -> web.Response:
            """Get list of available agents."""
            # Auto-generate node/model knowledge on first access (async-safe)
            if not self._auto_knowledge_generated:
                self._auto_knowledge_generated = True
                try:
                    await generate_auto_knowledge()
                    self.knowledge_manager.load_all()  # Reload with auto + prompting files
                    logger.info("Auto-generated knowledge from ComfyUI installation")
                except Exception as e:
                    logger.warning("Auto knowledge generation failed: %s", e)
                # Sync official templates on first load (if not already downloaded)
                try:
                    from .templates.sync_official import sync as sync_official, OUTPUT_DIR
                    official_count = len(list(OUTPUT_DIR.glob("*.json"))) if OUTPUT_DIR.exists() else 0
                    if official_count <= 1:  # Only index.json or empty
                        synced = sync_official()
                        logger.info("Synced %d official workflow templates", synced)
                except Exception as e:
                    logger.warning("Official template sync failed: %s", e)
                # Index local user workflows + official templates
                try:
                    count = self.workflow_registry.load()
                    logger.info("Workflow registry: indexed %d workflows", count)
                except Exception as e:
                    logger.warning("Workflow registry failed: %s", e)
            agents = await AgentRegistry.get_available_agents()
            return web.json_response(agents)

        @routes.get("/luna/system")
        async def get_system_info(request: web.Request) -> web.Response:
            """Get system information (GPU, models, etc.)."""
            gpu_info = await SystemMonitor.get_gpu_info()
            return web.json_response(gpu_info)

        @routes.get("/luna/models")
        async def get_models(request: web.Request) -> web.Response:
            """Get available ComfyUI models (all types, dynamic discovery)."""
            try:
                from .knowledge.auto_generator import discover_all_model_types
                models = await discover_all_model_types()
                if models:
                    return web.json_response(models)
            except Exception:
                pass
            # Fallback to SystemMonitor
            models = await SystemMonitor.get_available_models()
            return web.json_response(models)

        @routes.get("/luna/custom-nodes")
        async def get_custom_nodes(request: web.Request) -> web.Response:
            """Get installed custom nodes information."""
            custom_nodes = await SystemMonitor.get_installed_custom_nodes()
            return web.json_response(custom_nodes)

        @routes.get("/luna/knowledge-categories")
        async def get_knowledge_categories(request: web.Request) -> web.Response:
            """Get available knowledge categories for UI checkboxes."""
            categories = self.knowledge_manager.get_all_categories()
            return web.json_response(categories)

        @routes.get("/luna/node-info")
        async def get_node_info(request: web.Request) -> web.Response:
            """Get available node types from the registry."""
            await self.node_registry.fetch()
            class_types = self.node_registry.get_all_class_types()
            return web.json_response({
                "loaded": self.node_registry.is_loaded,
                "node_count": len(class_types),
                "class_types": class_types[:200],  # Limit response size
            })

        @routes.post("/luna/validate-workflow")
        async def validate_workflow(request: web.Request) -> web.Response:
            """Validate a workflow without applying it."""
            data = await request.json()
            workflow = data.get("workflow", {})

            # Try to fetch registry if not loaded
            await self.node_registry.fetch()

            result = self.validator.validate(workflow)
            return web.json_response({
                "valid": result.valid,
                "node_count": result.node_count,
                "validated_against_registry": result.validated_against_registry,
                "errors": [
                    {"check": i.check, "node_id": i.node_id,
                     "message": i.message, "suggestion": i.suggestion}
                    for i in result.errors
                ],
                "warnings": [
                    {"check": i.check, "node_id": i.node_id,
                     "message": i.message, "suggestion": i.suggestion}
                    for i in result.warnings
                ],
            })

        @routes.post("/luna/chat")
        async def chat(request: web.Request) -> web.StreamResponse:
            """Chat with an agent (streaming response with auto-correction)."""
            data = await request.json()

            agent_name = data.get("agent", "ollama")
            message = data.get("message", "")
            history = data.get("history", [])
            current_workflow = data.get("current_workflow")
            selected_model = data.get("model")
            context_mode = data.get("context_mode", "standard")
            knowledge_categories = data.get("knowledge_categories")
            raw_images = data.get("images", [])  # [{data, media_type, filename?}]

            # Get the agent backend
            agent = AgentRegistry.get(agent_name)
            if not agent:
                return web.json_response(
                    {"error": f"Agent '{agent_name}' not found"},
                    status=404
                )

            # Check availability
            if not await agent.is_available():
                return web.json_response(
                    {"error": f"Agent '{agent_name}' is not available"},
                    status=503
                )

            # Build knowledge context
            categories_enabled = set(knowledge_categories) if knowledge_categories else None
            model_name = selected_model or ""
            knowledge_text = self.knowledge_manager.build_knowledge_text(
                message=message,
                agent_name=agent_name,
                model_name=model_name,
                context_mode=context_mode,
                categories_enabled=categories_enabled,
            )

            # Build system context
            system_context = await self._build_system_context()

            # Build workflow context
            workflow_context = ""
            if current_workflow:
                verbose = context_mode != "minimal"
                # Try to use API format for more accurate context
                api_wf = self._convert_ui_to_api_format(current_workflow)
                if api_wf:
                    workflow_context = self._build_workflow_context_api(api_wf, verbose=verbose)
                else:
                    workflow_context = self._build_workflow_context(current_workflow, verbose=verbose)

            # Classify intent and get strategy hint
            plan = classify_intent(message)
            strategy_note = get_strategy_note(plan)

            # Compose full system prompt
            base_prompt = agent.get_base_system_prompt()
            full_prompt = base_prompt
            if strategy_note:
                full_prompt += strategy_note
            if knowledge_text:
                full_prompt += "\n\n" + knowledge_text
            full_prompt += "\n\n" + system_context
            if workflow_context:
                full_prompt += "\n\n" + workflow_context

            # Reinforce tool usage at end of prompt (recency effect)
            full_prompt += (
                "\n\n## REMINDER\n"
                "ALWAYS use tools before answering. Never guess model names, node names, "
                "or workflow details from context above. Call get_current_workflow(), "
                "get_model_metadata(), get_node_info() to verify facts before responding."
            )

            # Build messages list
            messages = []
            for msg in history:
                # Reconstruct images from history if present
                hist_images = None
                if msg.get("images"):
                    hist_images = []
                    for img in msg["images"]:
                        mt = img.get("media_type", "image/png")
                        if mt not in ALLOWED_IMAGE_TYPES:
                            mt = "image/png"
                        hist_images.append(ImageAttachment(
                            data=img["data"],
                            media_type=mt,
                            filename=img.get("filename"),
                        ))
                    hist_images = hist_images or None
                messages.append(AgentMessage(
                    role=msg.get("role", "user"),
                    content=msg.get("content", ""),
                    images=hist_images,
                ))

            # Parse image attachments for current message
            image_attachments = None
            if raw_images and agent.supports_vision:
                image_attachments = []
                for img in raw_images:
                    mt = img.get("media_type", "image/png")
                    if mt not in ALLOWED_IMAGE_TYPES:
                        mt = "image/png"
                    image_attachments.append(ImageAttachment(
                        data=img["data"],
                        media_type=mt,
                        filename=img.get("filename"),
                    ))
                image_attachments = image_attachments or None
            messages.append(AgentMessage(
                role="user", content=message, images=image_attachments,
            ))

            config = AgentConfig(
                model=selected_model,
                system_prompt=full_prompt,
            )

            # Try to ensure node registry is loaded for validation
            await self.node_registry.fetch()

            # Create streaming response
            response = web.StreamResponse(
                status=200,
                reason="OK",
                headers={
                    "Content-Type": "text/plain; charset=utf-8",
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                }
            )
            await response.prepare(request)

            # Make current workflow available to tools
            # Convert UI format (LiteGraph) to API format for tools
            if current_workflow:
                api_workflow = self._convert_ui_to_api_format(current_workflow)
                set_current_workflow(api_workflow if api_workflow else current_workflow)

            try:
                full_response = ""

                # Use tool loop if backend supports it and tools are available
                if agent.supports_tool_calling and self._tools and config.tools_enabled:
                    full_response = await self._run_tool_loop(
                        agent, messages, config, self._tools, response
                    )
                else:
                    async for chunk in agent.query(messages, config):
                        full_response += chunk
                        await response.write(chunk.encode("utf-8"))

                # Check if manipulation tools made direct modifications
                pending_mods = get_pending_modifications()
                if pending_mods:
                    # Send modifications as a special marker the frontend can parse
                    # and apply directly to canvas nodes without replacing the workflow
                    mod_marker = "\n\n<!-- CANVAS_MODIFICATIONS:" + json.dumps(pending_mods) + " -->"
                    await response.write(mod_marker.encode("utf-8"))
                    full_response += mod_marker

                # Auto-correction for new workflows (not modifications)
                workflow_json = WorkflowManipulator.extract_workflow_from_response(full_response)
                if workflow_json and self.node_registry.is_loaded:
                    result = self.validator.validate(workflow_json)
                    if not result.valid and result.errors:
                        await self._run_correction_loop(
                            agent, messages, config, full_response,
                            result, response
                        )

            except Exception as e:
                await response.write(f"\n\nError: {str(e)}".encode("utf-8"))

            await response.write_eof()
            return response

        @routes.post("/luna/apply-workflow")
        async def apply_workflow(request: web.Request) -> web.Response:
            """Validate and prepare a workflow for application."""
            data = await request.json()
            workflow = data.get("workflow", {})

            # Basic structural validation
            manipulator = WorkflowManipulator(workflow)
            is_valid, errors = manipulator.validate()

            if not is_valid:
                return web.json_response({
                    "success": False,
                    "errors": errors
                }, status=400)

            # Registry-based validation if available
            await self.node_registry.fetch()
            if self.node_registry.is_loaded:
                result = self.validator.validate(workflow)
                if not result.valid:
                    return web.json_response({
                        "success": False,
                        "errors": [i.message for i in result.errors],
                        "warnings": [i.message for i in result.warnings],
                    }, status=400)

            return web.json_response({
                "success": True,
                "workflow": workflow,
                "node_count": len(workflow)
            })

        @routes.post("/luna/tool-approval")
        async def tool_approval(request: web.Request) -> web.Response:
            """Handle user approval/denial for tools that require it."""
            data = await request.json()
            approval_id = data.get("approval_id", "")
            approved = data.get("approved", False)

            future = self._pending_approvals.get(approval_id)
            if not future:
                return web.json_response({"error": "Unknown approval ID"}, status=404)

            future.set_result(approved)
            return web.json_response({"success": True})

        @routes.post("/luna/reset-chat")
        async def reset_chat(request: web.Request) -> web.Response:
            """Reset conversation state for a fresh chat."""
            self.conversations.clear()
            # Reset agent chat sessions (e.g., Gemini's thought_signature state)
            from .agents.registry import AgentRegistry
            for agent in AgentRegistry.get_all().values():
                if hasattr(agent, '_reset_chat_session'):
                    agent._reset_chat_session()
            return web.json_response({"success": True})

    async def _run_tool_loop(
        self,
        agent,
        messages: List[AgentMessage],
        config: AgentConfig,
        tools,
        stream_response: web.StreamResponse,
    ) -> str:
        """Run the tool calling loop.

        Sends messages to the agent with tools enabled. When the agent
        returns ToolCall objects, executes them and feeds results back.
        Loops until the agent returns only text or max rounds are hit.

        Returns the final accumulated text response.
        """
        current_messages = list(messages)
        full_text = ""
        tool_call_history = []  # Track tool names per round for loop detection

        for _round in range(MAX_TOOL_ROUNDS):
            text_parts = []
            tool_calls = []

            async for item in agent.query_with_tools(current_messages, config, tools):
                if isinstance(item, ToolCall):
                    tool_calls.append(item)
                else:
                    text_parts.append(item)
                    await stream_response.write(item.encode("utf-8"))

            round_text = "".join(text_parts)
            full_text += round_text

            if not tool_calls:
                # No tool calls — agent is done
                break

            # Loop detection: check if the same tool(s) are being called repeatedly
            round_tools = tuple(sorted(tc.name for tc in tool_calls))
            tool_call_history.append(round_tools)
            if len(tool_call_history) >= MAX_REPEAT_TOOL_CALLS:
                recent = tool_call_history[-MAX_REPEAT_TOOL_CALLS:]
                if all(r == recent[0] for r in recent):
                    logger.warning(
                        f"Loop detected: {recent[0]} called {MAX_REPEAT_TOOL_CALLS} "
                        f"times consecutively, breaking tool loop"
                    )
                    await stream_response.write(
                        f"\n\n(Stopped: repeated tool calls detected after {_round + 1} rounds)".encode("utf-8")
                    )
                    break

            # Record the assistant message with its tool calls
            current_messages.append(AgentMessage(
                role="assistant",
                content=round_text,
                tool_calls=tool_calls,
            ))

            # Execute each tool call and feed results back
            for tc in tool_calls:
                # Check if tool requires user approval
                tool_def = ToolRegistry.get(tc.name)
                if tool_def and tool_def.requires_approval:
                    result_content = await self._request_tool_approval(
                        tc, stream_response
                    )
                    if result_content is None:
                        # Approved — execute normally
                        result = await ToolRegistry.execute(tc)
                        result_content = result.content
                    # If not None, it's a denial message — use as-is
                else:
                    result = await ToolRegistry.execute(tc)
                    result_content = result.content

                # Truncate large tool responses to prevent context exhaustion
                if len(result_content) > MAX_TOOL_RESPONSE_CHARS:
                    result_content = (
                        result_content[:MAX_TOOL_RESPONSE_CHARS]
                        + f"\n... (truncated from {len(result_content)} chars)"
                    )
                logger.info(f"Tool {tc.name}({tc.arguments}) -> {len(result_content)} chars")
                current_messages.append(AgentMessage(
                    role="tool",
                    content=result_content,
                    tool_call_id=tc.id,
                    metadata={"tool_name": tc.name},
                ))

            # Trim older tool results to prevent context bloat across rounds
            # Keep last 4 messages intact, truncate older tool results to 500 chars
            if len(current_messages) > 10:
                cutoff = len(current_messages) - 4
                for i in range(cutoff):
                    msg = current_messages[i]
                    if msg.role == "tool" and len(msg.content) > 500:
                        current_messages[i] = AgentMessage(
                            role="tool",
                            content=msg.content[:500] + "\n...(truncated older result)",
                            tool_call_id=msg.tool_call_id,
                            metadata=msg.metadata,
                        )
        else:
            await stream_response.write(
                f"\n\n(Tool loop reached maximum of {MAX_TOOL_ROUNDS} rounds)".encode("utf-8")
            )

        return full_text

    async def _run_correction_loop(
        self,
        agent,
        original_messages: List[AgentMessage],
        config: AgentConfig,
        last_response: str,
        validation_result,
        stream_response: web.StreamResponse,
    ) -> None:
        """Run the auto-correction loop when validation fails."""
        for attempt in range(1, MAX_CORRECTION_RETRIES + 1):
            # Stream correction notice
            notice = f"\n\n---\n**Validation found {len(validation_result.errors)} error(s). Correcting (attempt {attempt}/{MAX_CORRECTION_RETRIES})...**\n\n"
            await stream_response.write(notice.encode("utf-8"))

            # Build correction message
            error_text = validation_result.format_for_agent()
            correction_messages = list(original_messages)
            correction_messages.append(AgentMessage(role="assistant", content=last_response))
            correction_messages.append(AgentMessage(role="user", content=error_text))

            # Get corrected response
            corrected_response = ""
            async for chunk in agent.query(correction_messages, config):
                corrected_response += chunk
                await stream_response.write(chunk.encode("utf-8"))

            # Validate the correction
            workflow_json = WorkflowManipulator.extract_workflow_from_response(corrected_response)
            if not workflow_json:
                # No workflow in response - agent might have explained the fix
                break

            result = self.validator.validate(workflow_json)
            if result.valid or not result.errors:
                # Fixed!
                await stream_response.write(
                    "\n\n**Workflow validated successfully.**\n".encode("utf-8")
                )
                break

            # Still errors - continue loop
            last_response = corrected_response
            validation_result = result

        else:
            # Max retries exceeded
            remaining = validation_result.format_for_agent()
            await stream_response.write(
                f"\n\n**Auto-correction could not fix all errors after {MAX_CORRECTION_RETRIES} attempts.**\n{remaining}\n".encode("utf-8")
            )

    async def _build_system_context(self) -> str:
        """Build system context string for agents."""
        lines = ["## CURRENT SYSTEM STATUS"]

        # GPU info
        gpu_info = await SystemMonitor.get_gpu_info()
        if gpu_info.get("available") and gpu_info.get("gpus"):
            gpu = gpu_info["gpus"][0]
            lines.append(
                f"**GPU**: {gpu['name']}, "
                f"{gpu['vram_free_mb']}MB VRAM free of {gpu['vram_total_mb']}MB"
            )
            vram_free = gpu['vram_free_mb']
            if vram_free < 6000:
                lines.append("  -> Low VRAM: Recommend SD 1.5, fp8 models, tiled VAE")
            elif vram_free < 10000:
                lines.append("  -> Medium VRAM: SDXL OK, video with fewer frames")
            elif vram_free < 16000:
                lines.append("  -> Good VRAM: FLUX fp8 OK, most video workflows")
            else:
                lines.append("  -> High VRAM: All models supported")
        else:
            lines.append("**GPU**: Information unavailable")

        # Available models (counts only — agent uses get_available_models tool for details)
        try:
            models = await SystemMonitor.get_available_models()
            model_counts = []
            for mtype in ("checkpoints", "loras", "vae", "controlnets", "upscale_models"):
                count = len(models.get(mtype, []))
                if count:
                    model_counts.append(f"{mtype}: {count}")
            if model_counts:
                lines.append(f"\n**Installed models**: {', '.join(model_counts)}")
                lines.append("  Use get_available_models() tool for names and details.")
        except Exception:
            pass

        # Custom nodes info
        try:
            custom_nodes = await SystemMonitor.get_installed_custom_nodes()
            if custom_nodes.get("found"):
                lines.append(f"\n**Custom nodes installed**: {custom_nodes['total_count']} packs")

                capabilities = custom_nodes.get("node_capabilities", {})
                if capabilities.get("video"):
                    lines.append(f"  - Video: {', '.join(capabilities['video'])}")
                if capabilities.get("face"):
                    lines.append(f"  - Face processing: {', '.join(capabilities['face'])}")
                if capabilities.get("upscale"):
                    lines.append(f"  - Upscaling: {', '.join(capabilities['upscale'])}")
                if capabilities.get("controlnet"):
                    lines.append(f"  - ControlNet: {', '.join(capabilities['controlnet'])}")

                missing = []
                if not capabilities.get("video"):
                    missing.append("video generation (AnimateDiff/WAN)")
                if not capabilities.get("face"):
                    missing.append("face processing (Impact-Pack)")
                if not capabilities.get("controlnet"):
                    missing.append("ControlNet preprocessors")

                if missing:
                    lines.append(f"\n  **Missing for full capability**: {', '.join(missing)}")
                    lines.append("  -> Suggest installation if user needs these features")
        except Exception:
            pass

        return "\n".join(lines)

    async def _request_tool_approval(
        self,
        tool_call: ToolCall,
        stream_response: web.StreamResponse,
    ) -> Optional[str]:
        """Request user approval for a tool call.

        Sends an approval marker in the stream, then waits for the frontend
        to call /luna/tool-approval with the decision.

        Returns None if approved (caller should execute the tool),
        or a denial message string if denied.
        """
        approval_id = str(uuid.uuid4())[:8]
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_approvals[approval_id] = future

        # Send approval request marker to frontend
        approval_data = json.dumps({
            "approval_id": approval_id,
            "tool_name": tool_call.name,
            "arguments": tool_call.arguments,
        })
        marker = f"\n<!-- TOOL_APPROVAL_NEEDED:{approval_data} -->"
        await stream_response.write(marker.encode("utf-8"))

        try:
            # Wait for user response (timeout after 60 seconds)
            approved = await asyncio.wait_for(future, timeout=60.0)
        except asyncio.TimeoutError:
            approved = False
            logger.warning("Tool approval timed out for %s", tool_call.name)
        finally:
            self._pending_approvals.pop(approval_id, None)

        if approved:
            # Send approval confirmation
            confirm = f"\n<!-- TOOL_APPROVED:{approval_id} -->"
            await stream_response.write(confirm.encode("utf-8"))
            return None  # Caller will execute the tool
        else:
            deny = f"\n<!-- TOOL_DENIED:{approval_id} -->"
            await stream_response.write(deny.encode("utf-8"))
            return json.dumps({
                "error": "User denied this web access request.",
                "tool": tool_call.name,
                "tip": "The user chose not to allow this web request. Use your existing knowledge or local tools instead.",
            })

    def _build_workflow_context_api(self, workflow: Dict[str, Any], verbose: bool = True) -> str:
        """Build context from API-format workflow (accurate named inputs)."""
        if not workflow:
            return "## CURRENT WORKFLOW\n(Empty workflow)"

        node_count = len(workflow)
        if not verbose:
            types = {}
            for nid, node in workflow.items():
                ct = node.get("class_type", "?")
                types[ct] = types.get(ct, 0) + 1
            type_list = ", ".join(f"{t}({c})" if c > 1 else t for t, c in sorted(types.items()))
            return f"## CURRENT WORKFLOW ({node_count} nodes): {type_list}"

        lines = [
            "## CURRENT WORKFLOW (User's active workflow in ComfyUI)",
            "The user has shared their current workflow. Use get_current_workflow() tool for full details.",
            "",
            f"**Node count**: {node_count}",
            "",
            "**Nodes**:",
        ]

        for node_id, node in workflow.items():
            ct = node.get("class_type", "Unknown")
            title = (node.get("_meta") or {}).get("title", ct)
            inputs = node.get("inputs", {})

            lines.append(f"\n[{node_id}] {title} ({ct}):")

            # Model-type input names — hide filenames to force tool usage
            _MODEL_INPUTS = {
                "ckpt_name", "lora_name", "vae_name", "clip_name",
                "unet_name", "model_name", "control_net_name",
                "style_model_name", "upscale_model", "ipadapter_file",
                "diffusion_model",
            }

            for inp_name, inp_val in inputs.items():
                if inp_name.startswith("_"):
                    continue  # skip internal fields
                if isinstance(inp_val, list) and len(inp_val) == 2:
                    # Connection — show as link
                    lines.append(f"  {inp_name}: -> node {inp_val[0]}[{inp_val[1]}]")
                elif inp_name in _MODEL_INPUTS and isinstance(inp_val, str) and inp_val:
                    # Hide model filenames — agent must use tools to inspect
                    lines.append(f"  {inp_name}: [model loaded — use get_current_workflow() for details]")
                else:
                    # Direct value — show it
                    display_val = inp_val
                    if isinstance(inp_val, str) and len(inp_val) > 150:
                        display_val = inp_val[:150] + "..."
                    lines.append(f"  {inp_name}: {display_val}")

        lines.append("")
        lines.append("Use modify_node_input() to change settings, or get_current_workflow() for the full JSON.")

        return "\n".join(lines)

    def _convert_ui_to_api_format(self, workflow: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert LiteGraph UI format to ComfyUI API format.

        UI format has: {nodes: [...], links: [...]} with widgets_values arrays.
        API format has: {"1": {class_type, inputs}, "2": ...} with named inputs.

        Uses the node registry to map widgets_values to proper input names.
        """
        nodes = workflow.get("nodes")
        links = workflow.get("links")
        if not isinstance(nodes, list):
            # Already in API format or unknown format
            if isinstance(workflow, dict) and any(
                isinstance(v, dict) and "class_type" in v for v in workflow.values()
            ):
                return workflow  # Already API format
            return None

        # Build link lookup: link_id → (source_node_id, source_slot, target_node_id, target_slot, type)
        link_map = {}
        if isinstance(links, list):
            for link in links:
                if isinstance(link, list) and len(link) >= 5:
                    link_id = link[0]
                    link_map[link_id] = {
                        "source_id": str(link[1]),
                        "source_slot": link[2],
                    }

        api_workflow = {}
        for node in nodes:
            if not isinstance(node, dict):
                continue

            node_id = str(node.get("id", ""))
            class_type = node.get("type", "")
            if not node_id or not class_type:
                continue

            # Skip special UI nodes (Reroute, Note, etc.)
            if class_type in ("Reroute", "Note", "PrimitiveNode"):
                continue

            inputs = {}

            # 1. Resolve connections from the node's input links
            node_inputs = node.get("inputs", [])
            if isinstance(node_inputs, list):
                for inp in node_inputs:
                    if not isinstance(inp, dict):
                        continue
                    inp_name = inp.get("name", "")
                    link_id = inp.get("link")
                    if inp_name and link_id is not None and link_id in link_map:
                        link_info = link_map[link_id]
                        inputs[inp_name] = [link_info["source_id"], link_info["source_slot"]]

            # 2. Map widgets_values to input names using the node registry
            widgets = node.get("widgets_values")
            if isinstance(widgets, list) and widgets:
                node_def = self.node_registry.get_node(class_type) if self.node_registry.is_loaded else None

                if node_def:
                    # Get ordered list of widget input names (non-connection inputs)
                    # Connection types are handled above, widgets are the rest
                    connection_types = {
                        "MODEL", "CLIP", "VAE", "CONDITIONING", "LATENT", "IMAGE",
                        "MASK", "CONTROL_NET", "UPSCALE_MODEL", "SIGMAS", "NOISE",
                        "SAMPLER", "GUIDER", "BBOX_DETECTOR", "SEGM_DETECTOR",
                        "SAM_MODEL", "DETAILER_PIPE", "BASIC_PIPE", "DETAILER_HOOK",
                    }

                    widget_names = []
                    # Required inputs first (in order)
                    for name, inp_def in node_def.inputs_required.items():
                        if inp_def.type not in connection_types and name not in inputs:
                            widget_names.append(name)
                    # Then optional inputs
                    for name, inp_def in node_def.inputs_optional.items():
                        if inp_def.type not in connection_types and name not in inputs:
                            widget_names.append(name)

                    # Map widgets_values to names
                    # widgets_values can include control_after_generate toggles
                    # which aren't real inputs — skip them by checking against known names
                    wi = 0  # widget index
                    for wname in widget_names:
                        if wi >= len(widgets):
                            break
                        val = widgets[wi]
                        wi += 1

                        # Skip "control_after_generate" values that follow seed-type inputs
                        # These are UI-only and show as "randomize"/"fixed"/"increment" etc.
                        if wname in ("seed", "noise_seed") and wi < len(widgets):
                            next_val = widgets[wi]
                            if isinstance(next_val, str) and next_val in (
                                "randomize", "fixed", "increment", "decrement"
                            ):
                                wi += 1  # skip the control toggle

                        inputs[wname] = val
                else:
                    # No registry info — store raw widgets as fallback
                    inputs["_widgets_values"] = widgets

            title = node.get("title", class_type)
            api_workflow[node_id] = {
                "class_type": class_type,
                "inputs": inputs,
                "_meta": {"title": title},
            }

        return api_workflow if api_workflow else None

    def _build_workflow_context(self, workflow: Dict[str, Any], verbose: bool = True) -> str:
        """Build context string from the current workflow.

        Args:
            workflow: The current workflow dict
            verbose: If False, return only a summary (for small models)
        """
        nodes = workflow.get("nodes", [])
        links = workflow.get("links", [])

        if not nodes:
            return "## CURRENT WORKFLOW\n(Empty workflow)"

        # Summary mode for small models
        if not verbose:
            node_types = {}
            for node in nodes:
                t = node.get("type", "Unknown")
                node_types[t] = node_types.get(t, 0) + 1
            type_list = ", ".join(
                f"{t}({c})" if c > 1 else t
                for t, c in sorted(node_types.items())
            )
            return f"## CURRENT WORKFLOW ({len(nodes)} nodes): {type_list}"

        # Detailed mode
        lines = ["## CURRENT WORKFLOW (User's active workflow in ComfyUI)"]
        lines.append("The user has shared their current workflow. Analyze it to provide accurate modifications.")
        lines.append("")
        lines.append(f"**Node count**: {len(nodes)}")
        lines.append(f"**Connection count**: {len(links) if links else 0}")
        lines.append("")

        # Group nodes by type
        node_types = {}
        for node in nodes:
            node_type = node.get("type", "Unknown")
            if node_type not in node_types:
                node_types[node_type] = []
            node_types[node_type].append(node)

        lines.append("**Nodes by type**:")
        for node_type, type_nodes in sorted(node_types.items()):
            lines.append(f"- {node_type}: {len(type_nodes)}")

        lines.append("")
        lines.append("**Node details**:")

        for node in nodes:
            node_type = node.get("type", "Unknown")
            node_id = node.get("id", "?")
            title = node.get("title", node_type)

            widgets = node.get("widgets_values", [])
            if widgets:
                lines.append(f"\n[{node_id}] {title} ({node_type}):")

                if "KSampler" in node_type:
                    self._extract_ksampler_params(lines, widgets, node)
                elif "EmptyLatentImage" in node_type:
                    self._extract_latent_params(lines, widgets)
                elif "CLIPTextEncode" in node_type or "CLIP" in node_type:
                    self._extract_clip_params(lines, widgets)
                elif "VAE" in node_type:
                    self._extract_vae_params(lines, widgets, node_type)
                elif "CheckpointLoader" in node_type:
                    self._extract_checkpoint_params(lines, widgets)
                elif "LoraLoader" in node_type:
                    self._extract_lora_params(lines, widgets)
                elif "ControlNet" in node_type:
                    self._extract_controlnet_params(lines, widgets)
                elif "Video" in node_type or "AnimateDiff" in node_type:
                    self._extract_video_params(lines, widgets, node_type)
                else:
                    if len(widgets) <= 5:
                        lines.append(f"  widgets: {widgets}")

        lines.append("")
        lines.append("When suggesting modifications, reference specific node IDs and parameter names.")
        lines.append("Provide the exact values to change (from -> to).")

        return "\n".join(lines)

    def _extract_ksampler_params(self, lines: List[str], widgets: List, node: Dict) -> None:
        param_names = ["seed", "steps", "cfg", "sampler_name", "scheduler", "denoise"]
        for i, name in enumerate(param_names):
            if i < len(widgets):
                lines.append(f"  {name}: {widgets[i]}")

    def _extract_latent_params(self, lines: List[str], widgets: List) -> None:
        param_names = ["width", "height", "batch_size"]
        for i, name in enumerate(param_names):
            if i < len(widgets):
                lines.append(f"  {name}: {widgets[i]}")

    def _extract_clip_params(self, lines: List[str], widgets: List) -> None:
        if widgets:
            text = str(widgets[0])
            if len(text) > 200:
                text = text[:200] + "..."
            lines.append(f"  prompt: \"{text}\"")

    def _extract_vae_params(self, lines: List[str], widgets: List, node_type: str) -> None:
        if "Tiled" in node_type and widgets:
            lines.append(f"  tile_size: {widgets[0] if widgets else 'default'}")

    def _extract_checkpoint_params(self, lines: List[str], widgets: List) -> None:
        if widgets:
            lines.append(f"  checkpoint: [model loaded — use get_current_workflow() for details]")

    def _extract_lora_params(self, lines: List[str], widgets: List) -> None:
        param_names = ["lora_name", "strength_model", "strength_clip"]
        for i, name in enumerate(param_names):
            if i < len(widgets):
                if name == "lora_name":
                    lines.append(f"  {name}: [model loaded — use get_current_workflow() for details]")
                else:
                    lines.append(f"  {name}: {widgets[i]}")

    def _extract_controlnet_params(self, lines: List[str], widgets: List) -> None:
        param_names = ["strength", "start_percent", "end_percent"]
        for i, name in enumerate(param_names):
            if i < len(widgets):
                lines.append(f"  {name}: {widgets[i]}")

    def _extract_video_params(self, lines: List[str], widgets: List, node_type: str) -> None:
        if "AnimateDiff" in node_type:
            lines.append(f"  (AnimateDiff node with {len(widgets)} parameters)")
        elif "Video" in node_type:
            for i, val in enumerate(widgets[:5]):
                lines.append(f"  param_{i}: {val}")


# Global controller instance
controller = LunaCoreController()
