"""Intent planner for Comfy Luna Core.

Classifies user intent before routing to the agent, so the system can
pre-select relevant knowledge and suggest a strategy. This runs as a
fast local classifier — no LLM call needed.
"""

import re
from dataclasses import dataclass, field
from typing import List, Set


@dataclass
class PlanResult:
    """Result of intent classification."""

    intent: str  # primary intent: inspect, build, modify, repair, explain, prompt
    confidence: float  # 0.0 - 1.0
    suggested_tools: List[str] = field(default_factory=list)
    knowledge_hints: List[str] = field(default_factory=list)
    notes: str = ""


# Intent patterns: (regex, intent, confidence_boost, suggested_tools, knowledge_hints)
_PATTERNS = [
    # BUILD: create new workflow from scratch
    (r"\b(create|build|make|generate|set up|setup)\b.*\b(workflow|pipeline|graph)\b",
     "build", 0.8, ["search_workflows", "get_node_types", "get_available_models"],
     ["workflow templates", "prompting"]),
    (r"\b(new|start|begin|blank)\b.*\b(workflow|canvas)\b",
     "build", 0.7, ["search_workflows", "get_node_types", "get_available_models"],
     ["workflow templates"]),
    (r"\b(txt2img|img2img|text.to.image|image.to.image|t2i|i2i)\b",
     "build", 0.6, ["search_workflows", "get_available_models"],
     ["workflow templates", "prompting"]),

    # MODIFY: change existing workflow settings
    (r"\b(change|modify|update|set|adjust|increase|decrease|lower|raise|switch)\b.*\b(steps|cfg|sampler|scheduler|model|checkpoint|lora|resolution|width|height|denoise|seed)\b",
     "modify", 0.9, ["get_current_workflow", "get_node_info", "modify_node_input"],
     []),
    (r"\b(add|insert|include)\b.*\b(node|lora|controlnet|upscale)\b",
     "modify", 0.8, ["get_current_workflow", "get_node_types", "add_node", "connect_nodes"],
     []),
    (r"\b(remove|delete|disconnect)\b.*\b(node|lora|connection)\b",
     "modify", 0.8, ["get_current_workflow", "remove_node"],
     []),
    (r"\b(connect|wire|link)\b.*\b(node|output|input)\b",
     "modify", 0.8, ["get_current_workflow", "get_node_info", "connect_nodes"],
     []),

    # REPAIR: fix errors or broken workflow
    (r"\b(fix|repair|debug|broken|error|fail|crash|not work|doesn.t work|wrong)\b",
     "repair", 0.8, ["get_current_workflow", "get_node_info"],
     []),
    (r"\b(why|what.s wrong|what happened|problem)\b",
     "repair", 0.5, ["get_current_workflow"],
     []),

    # INSPECT: look at current state
    (r"\b(show|list|what|which|tell me|describe)\b.*\b(models?|checkpoints?|loras?|nodes?|workflow|canvas|settings?)\b",
     "inspect", 0.7, ["get_current_workflow", "get_available_models", "get_node_types"],
     []),
    (r"\b(current|active|loaded)\b.*\b(workflow|model|settings?)\b",
     "inspect", 0.7, ["get_current_workflow"],
     []),

    # PROMPT: help with prompting
    (r"\b(prompt|prompting|write.*prompt|help.*prompt|negative.*prompt)\b",
     "prompt", 0.8, ["get_current_workflow", "get_model_metadata"],
     ["prompting"]),
    (r"\b(trigger\s*words?|tags?|quality\s*tags?|score\s*tags?)\b",
     "prompt", 0.7, ["get_model_metadata"],
     ["prompting"]),

    # EXPLAIN: general questions
    (r"\b(explain|how does|what is|what are|difference between)\b",
     "explain", 0.6, [],
     []),
]


def classify_intent(message: str) -> PlanResult:
    """Classify the user's intent from their message.

    Returns a PlanResult with the best-matching intent, suggested tools
    to prioritize, and knowledge categories to load.
    """
    message_lower = message.lower().strip()

    best: PlanResult = PlanResult(intent="general", confidence=0.0)

    for pattern, intent, confidence, tools, hints in _PATTERNS:
        if re.search(pattern, message_lower):
            if confidence > best.confidence:
                best = PlanResult(
                    intent=intent,
                    confidence=confidence,
                    suggested_tools=tools,
                    knowledge_hints=hints,
                )

    # If no pattern matched, try some simple heuristics
    if best.confidence == 0.0:
        if "?" in message:
            best = PlanResult(intent="explain", confidence=0.3)
        elif any(word in message_lower for word in ("please", "can you", "could you", "help")):
            best = PlanResult(intent="general", confidence=0.2)

    return best


def get_strategy_note(plan: PlanResult) -> str:
    """Generate a brief strategy note for the agent based on the plan.

    This gets injected into the system prompt as a hint about what the
    user likely wants.
    """
    strategies = {
        "build": "User wants to create a workflow. Search their saved workflows first (search_workflows), check available models, then adapt a template.",
        "modify": "User wants to change the current workflow. Read it first (get_current_workflow), verify inputs with get_node_info, then apply changes.",
        "repair": "User has a problem. Read the current workflow, check for errors, and diagnose before suggesting fixes.",
        "inspect": "User wants information. Use discovery tools to answer their question.",
        "prompt": "User needs prompting help. Check the model metadata for trigger words and base model, then use the prompting knowledge for that model family.",
        "explain": "User is asking a question. Answer from your knowledge, reference actual ComfyUI behavior.",
    }

    note = strategies.get(plan.intent, "")
    if note and plan.confidence >= 0.5:
        return f"\n[Strategy hint: {note}]"
    return ""
