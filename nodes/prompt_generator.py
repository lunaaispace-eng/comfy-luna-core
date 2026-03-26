"""Prompt generator node using AI agents."""

import asyncio
import concurrent.futures
import re
from typing import Tuple

from ..agents import AgentRegistry, AgentMessage, AgentConfig


# Thread pool for running async agent calls from ComfyUI's sync node execution
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)


def _run_async(coro):
    """Run an async coroutine from synchronous ComfyUI node context.

    ComfyUI nodes execute synchronously, but the agent backends are async.
    We spin up a fresh event loop in a worker thread to avoid conflicts
    with ComfyUI's own asyncio loop.
    """
    def _worker():
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    future = _executor.submit(_worker)
    return future.result(timeout=120)


class AgenticPromptGenerator:
    """ComfyUI node that generates or enhances prompts using AI agents.

    Input a simple description and get a detailed, optimized prompt
    suitable for image generation.
    """

    CATEGORY = "luna-core"
    FUNCTION = "generate"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("positive_prompt", "negative_prompt")

    @classmethod
    def INPUT_TYPES(cls):
        agents = list(AgentRegistry.get_all().keys()) or ["ollama"]

        return {
            "required": {
                "description": ("STRING", {
                    "multiline": True,
                    "default": "A beautiful landscape"
                }),
                "agent": (agents, {"default": agents[0] if agents else "ollama"}),
                "style": ([
                    "photorealistic",
                    "artistic",
                    "anime",
                    "digital art",
                    "oil painting",
                    "watercolor",
                    "sketch",
                    "3d render",
                    "none"
                ], {"default": "photorealistic"}),
            },
            "optional": {
                "model": ("STRING", {
                    "default": "",
                    "tooltip": "Model name to use (leave empty for agent default)"
                }),
                "additional_instructions": ("STRING", {
                    "multiline": True,
                    "default": ""
                }),
            }
        }

    def generate(
        self,
        description: str,
        agent: str,
        style: str,
        model: str = "",
        additional_instructions: str = ""
    ) -> Tuple[str, str]:
        """Generate positive and negative prompts from a description."""
        return _run_async(
            self._generate_async(
                description, agent, style, model, additional_instructions
            )
        )

    async def _generate_async(
        self,
        description: str,
        agent_name: str,
        style: str,
        model: str,
        additional_instructions: str
    ) -> Tuple[str, str]:
        """Async implementation of prompt generation."""

        agent = AgentRegistry.get(agent_name)
        if not agent or not await agent.is_available():
            positive = f"{description}, {style}, high quality, detailed"
            negative = "blurry, low quality, distorted"
            return (positive, negative)

        system_prompt = """You are a prompt engineer for Stable Diffusion and FLUX image generation models.

Your task is to convert simple descriptions into optimized prompts.

Rules:
1. Output EXACTLY two clearly labeled lines:
   POSITIVE: <the positive prompt>
   NEGATIVE: <the negative prompt>
2. Do not include any other text, explanations, or formatting
3. Use comma-separated tags and descriptors
4. Include quality boosters like "masterpiece, best quality, highly detailed"
5. The negative prompt should include common issues to avoid

Example output:
POSITIVE: masterpiece, best quality, a serene mountain lake at sunset, golden hour lighting, reflection on water, pine trees, snow-capped peaks, photorealistic, 8k, highly detailed
NEGATIVE: blurry, low quality, distorted, watermark, signature, text, ugly, deformed, disfigured"""

        style_instruction = f"Apply a {style} style." if style != "none" else ""
        extra = f"\nAdditional requirements: {additional_instructions}" if additional_instructions else ""

        message = f"Create prompts for: {description}\n{style_instruction}{extra}"

        messages = [AgentMessage(role="user", content=message)]
        config = AgentConfig(
            system_prompt=system_prompt,
            model=model or None,
            temperature=0.7,
            max_tokens=500,
        )

        response = ""
        async for chunk in agent.query(messages, config):
            response += chunk

        return self._parse_response(response, description, style)

    @staticmethod
    def _parse_response(
        response: str, description: str, style: str
    ) -> Tuple[str, str]:
        """Parse the agent response into positive/negative prompts.

        Handles various output formats:
          - POSITIVE: ... / NEGATIVE: ...
          - Positive prompt: ... / Negative prompt: ...
          - Two plain lines
        """
        positive = ""
        negative = ""

        # Try labeled format first (case-insensitive)
        pos_match = re.search(
            r"(?:positive|positive prompt)[:\s]*(.+)",
            response, re.IGNORECASE,
        )
        neg_match = re.search(
            r"(?:negative|negative prompt)[:\s]*(.+)",
            response, re.IGNORECASE,
        )

        if pos_match:
            positive = pos_match.group(1).strip()
        if neg_match:
            negative = neg_match.group(1).strip()

        # Fallback: take first two non-empty, non-label lines
        if not positive:
            lines = [
                l.strip() for l in response.strip().split("\n")
                if l.strip() and not l.strip().startswith(("#", "```", "---"))
            ]
            if lines:
                positive = lines[0]
            if len(lines) >= 2 and not negative:
                negative = lines[1]

        # Last resort fallback
        if not positive:
            positive = f"{description}, {style}, high quality, detailed, masterpiece"
        if not negative:
            negative = "blurry, low quality, distorted, watermark, text, ugly, deformed"

        # Clean up any leftover label prefixes
        for prefix in ("POSITIVE:", "NEGATIVE:", "Positive:", "Negative:",
                       "positive prompt:", "negative prompt:",
                       "Positive Prompt:", "Negative Prompt:"):
            positive = positive.removeprefix(prefix).strip()
            negative = negative.removeprefix(prefix).strip()

        return (positive, negative)
