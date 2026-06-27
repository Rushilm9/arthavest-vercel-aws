"""
Backfill: reconcile stored narratives with the final verdict.

Historical Recommendations rows written before the verdict/narrative fix may have a
`full_response.narrative` (and `final_narrative`) whose declared decision disagrees
with the row's final verdict — e.g. verdict BUY but the prose says "the final
decision is to WAIT". This script finds those rows and prepends a corrected decision
sentence so the detail view matches the badge. It also normalizes the verdict label
(HOLD -> WAIT) in both the column and the snapshot.

Usage:
    python -m scripts.backfill_verdict_narrative            # dry-run (report only)
    python -m scripts.backfill_verdict_narrative --apply    # write changes
    python -m scripts.backfill_verdict_narrative --apply --limit 50

Safe to re-run: once a row is corrected it no longer contradicts, so it is skipped.
"""

import argparse
import copy

from app.core.config import SessionLocal, logger
from app.core.verdict import final_verdict, narrative_contradicts_verdict
from app.db.models import Recommendations, Stocks


def _corrected_first_bullet(symbol: str, verdict: str, confidence) -> str:
    conf = f"{confidence}%" if confidence is not None else "the stated level"
    if verdict == "WAIT":
        return (
            f"<li>The final decision is to <b>WAIT</b> on {symbol} with a "
            f"confidence of <strong>{conf}</strong> — no trade is taken at this "
            f"time.</li>"
        )
    article = "an" if verdict[0] in "AEIOU" else "a"
    return (
        f"<li>The final decision is {article} <b>{verdict}</b> for {symbol} "
        f"with a confidence of <strong>{conf}</strong>.</li>"
    )


def _fix_narrative(narrative: str, bullet: str) -> str:
    narrative = narrative or ""
    if "<ul>" in narrative:
        return narrative.replace("<ul>", "<ul>" + bullet, 1)
    return f"<ul>{bullet}</ul>" + narrative


def run(apply: bool, limit: int | None):
    db = SessionLocal()
    scanned = mismatched = fixed = 0
    try:
        q = (
            db.query(Recommendations, Stocks.symbol)
            .join(Stocks, Recommendations.stock_id == Stocks.id)
            .order_by(Recommendations.created_at.desc())
        )
        if limit:
            q = q.limit(limit)
        rows = q.all()

        for rec, sym in rows:
            scanned += 1
            verdict = final_verdict(rec.recommendation)
            conf = rec.confidence

            fr = rec.full_response if isinstance(rec.full_response, dict) else None
            narr_snapshot = (fr or {}).get("narrative") if fr else None
            narr_column = rec.final_narrative or (rec.reasoning or {}).get("narrative")

            snap_bad = narr_snapshot and narrative_contradicts_verdict(
                narr_snapshot, verdict
            )
            col_bad = narr_column and narrative_contradicts_verdict(
                narr_column, verdict
            )
            label_bad = (rec.recommendation or "").upper() not in (
                "BUY",
                "SELL",
                "WAIT",
            )

            if not (snap_bad or col_bad or label_bad):
                continue

            mismatched += 1
            print(
                f"  [{'FIX' if apply else 'DRY'}] {sym} {str(rec.id)[:8]} "
                f"verdict={verdict} snap_bad={bool(snap_bad)} col_bad={bool(col_bad)} "
                f"label_bad={label_bad}"
            )

            if not apply:
                continue

            bullet = _corrected_first_bullet(sym, verdict, conf)

            # Normalize the column label.
            rec.recommendation = verdict

            # Fix the snapshot narrative + its verdict label.
            if fr is not None:
                new_fr = copy.deepcopy(fr)
                new_fr["recommendation"] = verdict
                if snap_bad:
                    new_fr["narrative"] = _fix_narrative(narr_snapshot, bullet)
                rec.full_response = new_fr  # reassign so SQLAlchemy detects the change

            # Fix the column narrative.
            if col_bad:
                rec.final_narrative = _fix_narrative(narr_column, bullet)
                if isinstance(rec.reasoning, dict) and rec.reasoning.get("narrative"):
                    new_reasoning = copy.deepcopy(rec.reasoning)
                    new_reasoning["narrative"] = _fix_narrative(
                        new_reasoning["narrative"], bullet
                    )
                    rec.reasoning = new_reasoning

            fixed += 1

        if apply:
            db.commit()
        print(
            f"\nscanned={scanned} mismatched={mismatched} fixed={fixed} "
            f"({'APPLIED' if apply else 'DRY-RUN — re-run with --apply'})"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"[red]Backfill failed: {e}[/red]")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--apply", action="store_true", help="write changes (default: dry-run)"
    )
    ap.add_argument(
        "--limit", type=int, default=None, help="only scan the N most recent rows"
    )
    args = ap.parse_args()
    run(apply=args.apply, limit=args.limit)
