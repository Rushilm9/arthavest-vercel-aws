"""Write one deterministic eval annotation onto the decision span. Fail-soft.

Uses the Phoenix Cloud REST client to annotate the BUY/SELL/WAIT decision span
with a `decision_quality` score, making it visible in the Phoenix Cloud UI.

The retry loop handles the async span-indexing race: spans arrive via OTel and
are indexed asynchronously (several seconds). Annotating immediately after the
run often hits a "span not found" because it hasn't been indexed yet.
"""

import time
from app.core.config import settings, logger

_MAX_RETRIES = 10
_RETRY_DELAY_SEC = 4


def annotate_decision(span_id: str, passed: bool, explanation: str):
    """Annotate the decision span with a deterministic eval result.

    Args:
        span_id: hex span ID from OpenTelemetry (format: 016x of the span_id int).
        passed: True if the decision meets quality criteria (validator accepted + confidence ok).
        explanation: Human-readable reason for the PASS/FAIL label.
    """
    if not settings.ARIZE_ENABLED or not span_id:
        return
    try:
        from phoenix.client import Client

        endpoint = (
            settings.PHOENIX_COLLECTOR_ENDPOINT or "https://app.phoenix.arize.com"
        )
        base_url = "https://app.phoenix.arize.com"
        if endpoint and "/v1/traces" in endpoint:
            base_url = endpoint.split("/v1/traces")[0]
        else:
            base_url = endpoint
        client = Client(
            base_url=base_url,
            api_key=settings.PHOENIX_API_KEY or None,
        )

        label = "PASS" if passed else "FAIL"
        score = 1.0 if passed else 0.0

        for attempt in range(_MAX_RETRIES):
            try:
                client.spans.add_span_annotation(
                    span_id=span_id,
                    annotation_name="decision_quality",
                    label=label,
                    score=score,
                    explanation=explanation,
                )
                logger.info(
                    f"[bold green]✅ Eval annotation: decision_quality={label} "
                    f"(score={score}) on span {span_id}[/bold green]"
                )
                return
            except Exception:
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_RETRY_DELAY_SEC)
                # On last attempt, fall through to the warning below

        logger.warning(
            "[yellow]Eval annotation: span not indexed after retries (non-fatal).[/yellow]"
        )
    except Exception as e:
        logger.warning(f"[yellow]Eval annotation failed (non-fatal): {e}[/yellow]")
