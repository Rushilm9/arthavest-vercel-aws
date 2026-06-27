"""
Model Router — single source of truth for all LLM model selection.

Maps each agent to the correct Gemini tier per MODELS.MD.
Enforces the use of Vertex AI exclusively.
"""

import contextvars
from enum import Enum
from typing import Optional

from app.core.config import settings, logger

# ── Per-invocation token accounting ──────────────────────────────────────────
# A LangChain callback (TokenUsageCollector) writes token counts here on every
# on_llm_end. The track_agent decorator resets this at node entry and reads it
# after the node returns, so each agent_logs row gets real tokens — without
# editing any individual agent. Node + its .invoke() run on the same thread, so a
# ContextVar set at node entry is visible to the callback during that invoke.
_token_acc: "contextvars.ContextVar[dict]" = contextvars.ContextVar(
    "_token_acc", default=None
)


def reset_token_accumulator() -> None:
    _token_acc.set({"input": 0, "output": 0})


def read_token_accumulator() -> dict:
    acc = _token_acc.get()
    return dict(acc) if acc else {"input": 0, "output": 0}


def _add_tokens(ti: int, to: int) -> None:
    acc = _token_acc.get()
    if acc is None:
        return  # not inside a tracked node — ignore
    acc["input"] += int(ti or 0)
    acc["output"] += int(to or 0)


try:
    from langchain_core.callbacks.base import BaseCallbackHandler

    class TokenUsageCollector(BaseCallbackHandler):
        """Accumulates token usage from every LLM call into the _token_acc ContextVar."""

        def on_llm_end(self, response, **kwargs):
            try:
                # Sum usage across generations; both Vertex and GenAI expose
                # usage_metadata on the message, and/or llm_output token counts.
                ti = to = 0
                llm_out = getattr(response, "llm_output", None) or {}
                usage = (
                    llm_out.get("usage_metadata") or llm_out.get("token_usage") or {}
                )
                ti += int(
                    usage.get("input_tokens", usage.get("prompt_token_count", 0)) or 0
                )
                to += int(
                    usage.get("output_tokens", usage.get("candidates_token_count", 0))
                    or 0
                )
                if not (ti or to):
                    for gen_list in getattr(response, "generations", None) or []:
                        for gen in gen_list:
                            msg = getattr(gen, "message", None)
                            um = getattr(msg, "usage_metadata", None) or {}
                            ti += int(um.get("input_tokens", 0) or 0)
                            to += int(um.get("output_tokens", 0) or 0)
                _add_tokens(ti, to)
            except Exception:
                pass  # token accounting must never break an LLM call

    _TOKEN_COLLECTOR = TokenUsageCollector()
except Exception:
    _TOKEN_COLLECTOR = None

try:
    from langchain_google_vertexai import ChatVertexAI

    _VERTEX_AVAILABLE = True
    # langchain + pydantic v2 lazily defines ChatVertexAI; under some import orders
    # the class is left "not fully defined" (BaseCache forward-ref unresolved), and
    # the FIRST .invoke() raises PydanticUserError mid-pipeline (observed killing the
    # news node). Resolve the forward refs once, now, so every model instance is
    # usable. Importing BaseCache makes it available for the rebuild's namespace.
    try:
        from langchain_core.caches import BaseCache  # noqa: F401  (needed for model_rebuild)
        from langchain_core.callbacks import Callbacks  # noqa: F401

        ChatVertexAI.model_rebuild()
    except Exception:
        # Non-fatal: if rebuild isn't needed on this version, the class already works.
        pass
except ImportError:
    ChatVertexAI = None
    _VERTEX_AVAILABLE = False


class ModelTier(str, Enum):
    FLASH_LITE = "flash_lite"  # economic node (very cheap extraction)
    FLASH = (
        "flash"  # market_pulse, news, technical, fundamental, sentiment, chart_pattern
    )
    PRO = "pro"  # macro_context, planner, decision
    PRO_THINK = "pro_think"  # debate only (thinking_budget=8192)


# ── Stable model IDs ────────────────────────────────────────────────────────
_MODEL_IDS: dict[ModelTier, str] = {
    ModelTier.FLASH_LITE: "gemini-3.1-flash-lite",
    ModelTier.FLASH: "gemini-3.1-flash-lite",
    ModelTier.PRO: "gemini-3.1-flash-lite",
    ModelTier.PRO_THINK: "gemini-3.1-flash-lite",
}

_VERTEX_MODEL_IDS: dict[ModelTier, str] = {
    ModelTier.FLASH_LITE: "gemini-2.5-flash",
    ModelTier.FLASH: "gemini-2.5-flash",
    ModelTier.PRO: "gemini-2.5-pro",
    ModelTier.PRO_THINK: "gemini-2.5-pro",
}


# Default output-token ceiling. Without this the model uses a low default cap and
# large JSON responses get truncated mid-object → JSON fails to parse → 0 results.
_DEFAULT_MAX_OUTPUT_TOKENS = 32768


# gemini-2.5-* are THINKING models: by default they spend a large, input-scaled
# share of the output-token budget on internal reasoning tokens (measured ~28k
# reasoning for a 75-stock discovery classify). That budget is consumed BEFORE
# the visible answer, so the JSON response truncates mid-object and fails to parse
# → 0 stocks. We minimise thinking by default for structured/extraction calls.
#
# IMPORTANT model differences (Vertex):
#   - gemini-2.5-flash  → supports thinking_budget=0 (fully off). Use 0.
#   - gemini-2.5-pro    → does NOT allow 0 (returns HTTP 400). Its minimum is 128,
#                         so we use that to keep reasoning tokens minimal.
# The PRO_THINK tier (debate) overrides this via `extra` (spread last) to re-enable
# a real thinking budget.
def _default_thinking_budget(model_id: str) -> int:
    return 0 if "flash" in model_id else 128


def _make_chat(model_id: str, json_mode: bool, extra: dict | None = None):
    extra = extra or {}
    # Attach the token-usage collector callback to every model instance so token
    # counts land in the _token_acc ContextVar on each .invoke(). Merge with any
    # caller-supplied callbacks rather than clobbering them.
    if _TOKEN_COLLECTOR is not None:
        cbs = list(extra.get("callbacks") or [])
        if _TOKEN_COLLECTOR not in cbs:
            cbs.append(_TOKEN_COLLECTOR)
        extra["callbacks"] = cbs
    if settings.USE_VERTEX:
        if not _VERTEX_AVAILABLE:
            raise RuntimeError(
                "USE_VERTEX=true is set, but 'langchain_google_vertexai' could not be imported. "
                "Please ensure the package is installed to satisfy Vertex AI exclusivity."
            )
        kwargs = {
            "model": model_id,
            "temperature": 0.0,
            "max_retries": 3,
            "max_output_tokens": _DEFAULT_MAX_OUTPUT_TOKENS,
            "thinking_budget": _default_thinking_budget(model_id),
            "project": settings.GOOGLE_CLOUD_PROJECT,
            "location": settings.GOOGLE_CLOUD_LOCATION,
            **extra,
        }
        if json_mode:
            kwargs.setdefault("model_kwargs", {})["generation_config"] = {
                "response_mime_type": "application/json"
            }
        return ChatVertexAI(**kwargs)

    # Fallback if vertex disabled/unavailable
    from langchain_google_genai import ChatGoogleGenerativeAI

    api_key = settings.LLM_API_KEY_1 or "dummy_key"
    kwargs = {
        "model": model_id,
        "google_api_key": api_key,
        "temperature": 0.0,
        "max_retries": 3,
        "max_output_tokens": _DEFAULT_MAX_OUTPUT_TOKENS,
        **extra,
    }
    if json_mode:
        kwargs.setdefault("model_kwargs", {})["generation_config"] = {
            "response_mime_type": "application/json"
        }
    return ChatGoogleGenerativeAI(**kwargs)


# ── Cost rates (USD per token) ───────────────────────────────────────────────
COST_RATES_USD: dict[str, dict[str, float]] = {
    "gemini-2.5-flash": {"input": 0.00000010, "output": 0.00000040},
    "gemini-2.5-pro": {"input": 0.00000125, "output": 0.00001000},
    "gemini-3.1-flash-lite": {"input": 0.0, "output": 0.0},
}

USD_TO_INR_FALLBACK = 84.0


def compute_cost(model_id: str, tokens_in: int, tokens_out: int) -> float:
    """Returns cost in USD for a single LLM call."""
    rates = COST_RATES_USD.get(model_id, COST_RATES_USD["gemini-2.5-flash"])
    return round(tokens_in * rates["input"] + tokens_out * rates["output"], 8)


def cost_usd_to_inr(cost_usd: float, usd_inr: float = USD_TO_INR_FALLBACK) -> float:
    """Convert USD cost to INR."""
    return round(cost_usd * usd_inr, 4)


def get_model(
    tier: ModelTier,
    json_mode: bool = False,
    custom_key: Optional[str] = None,
    custom_model: Optional[str] = None,
):
    """
    Returns a ChatVertexAI instance for the given tier.
    """
    if custom_model:
        return _make_chat(custom_model, json_mode)

    if settings.USE_VERTEX:
        model_id = _VERTEX_MODEL_IDS.get(tier, _MODEL_IDS[tier])
    else:
        model_id = _MODEL_IDS[tier]

    kwargs_base: dict = {}
    if tier == ModelTier.PRO_THINK and "gemini-2.5-pro" in model_id:
        # Debate tier WANTS extended thinking. Override the _make_chat default of
        # thinking_budget=0 with the top-level constructor arg (the supported way
        # in langchain-google-vertexai; the old model_kwargs.thinking_config form
        # was silently ignored). Also raise the ceiling to fit thinking + answer.
        kwargs_base["thinking_budget"] = 8192
        kwargs_base["max_output_tokens"] = 16384

    return _make_chat(model_id, json_mode and tier != ModelTier.PRO_THINK, kwargs_base)


def get_model_id(tier: ModelTier) -> str:
    """Returns the model ID string for cost tracking / logging."""
    if settings.USE_VERTEX:
        return _VERTEX_MODEL_IDS.get(tier, _MODEL_IDS[tier])
    return _MODEL_IDS[tier]
