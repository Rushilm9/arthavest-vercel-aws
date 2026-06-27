"""Portable Arize Phoenix Cloud observability. No-op unless ARIZE_ENABLED=true.

This is the ONLY module that imports Phoenix. Nothing else in the codebase
touches it. If ARIZE_ENABLED is false OR the packages are missing, the app
runs exactly as it did before this file existed.
"""

from app.core.config import settings, logger

_initialized = False


def init_observability():
    """Wire LangChain auto-instrumentation to Phoenix Cloud. Idempotent + fail-soft."""
    global _initialized
    if _initialized:
        return
    if not settings.ARIZE_ENABLED:
        logger.info("[dim]Arize Phoenix disabled (ARIZE_ENABLED=false).[/dim]")
        return
    try:
        import warnings as _warnings
        from phoenix.otel import register
        from openinference.instrumentation.langchain import LangChainInstrumentor

        # Phoenix emits a cosmetic UserWarning when it can't infer the collector
        # protocol from the endpoint — it correctly defaults to HTTP, which is
        # what we want, so silence the noise.
        _warnings.filterwarnings(
            "ignore",
            message=r".*Could not infer collector endpoint protocol.*",
        )

        # EXPLICIT register + instrument. We deliberately do NOT use
        # register(auto_instrument=True): explicit fails LOUDLY if the
        # instrumentor is missing, auto fails SILENTLY ("why no traces?").
        #
        # SimpleSpanProcessor (Phoenix default) exports each span IMMEDIATELY.
        # We intentionally do NOT use batch=True here: this is a dev/demo server
        # that gets force-killed between runs, so a BatchSpanProcessor would
        # buffer spans that never flush — you'd run /analyze and see nothing land
        # in the Phoenix dashboard. Immediate export is what we want for visible
        # traces. (The only cost is a "use BatchSpanProcessor in production"
        # startup notice, which is harmless.)
        if not settings.PHOENIX_COLLECTOR_ENDPOINT:
            logger.warning(
                "[yellow]PHOENIX_COLLECTOR_ENDPOINT is empty. Disabling tracing to prevent local server hang.[/yellow]"
            )
            return

        tp = register(
            project_name=settings.PHOENIX_PROJECT_NAME,
            endpoint=settings.PHOENIX_COLLECTOR_ENDPOINT,
            api_key=settings.PHOENIX_API_KEY or None,
        )
        LangChainInstrumentor().instrument(tracer_provider=tp)
        _initialized = True
        logger.info(
            "[bold green]✅ Arize Phoenix tracing ON → "
            f"{settings.PHOENIX_PROJECT_NAME}[/bold green]"
        )
    except Exception as e:
        # NEVER let observability crash the app — that's the whole point of the toggle.
        logger.warning(
            f"[yellow]Arize init failed (continuing WITHOUT tracing): {e}[/yellow]"
        )
