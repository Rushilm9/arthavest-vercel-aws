"""
Run and evaluate Phoenix Cloud Datasets & Experiments.
Generates interactive comparison charts and logs custom Evaluators natively on the Arize Phoenix Cloud UI.
"""

import os
import sys
import asyncio

# Ensure the project root (parent of this eval/ dir) is importable so `from
# app.agents...` works no matter where the script is launched from. Without this,
# running `python eval/run_experiment.py` (or the /api/improve/approve subprocess,
# which invokes it the same way) fails with ModuleNotFoundError: No module named 'app'.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import pandas as pd
from dotenv import load_dotenv
from phoenix.client import Client
from rich.console import Console
from rich.panel import Panel

# Make sure we use UTF-8
os.environ["PYTHONIOENCODING"] = "utf-8"

# Load environment
load_dotenv()

# Initialize Console with standard ASCII characters for full Windows compatibility
console = Console(legacy_windows=True)

console.print(
    Panel(
        "[bold green]=== ArthaVest Phoenix Cloud Dataset & Experiments Runner ===[/bold green]\n"
        "[dim]Programmatic evaluations and comparison charts uploaded directly to your Cloud space[/dim]",
        border_style="green",
        expand=False,
    )
)

# Compute cloud base url
endpoint = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT", "https://app.phoenix.arize.com")
base_url = "https://app.phoenix.arize.com"
if "/v1/traces" in endpoint:
    base_url = endpoint.split("/v1/traces")[0]
api_key = os.environ.get("PHOENIX_API_KEY")

console.print(
    f"[bold cyan][PXP] Connecting to Phoenix Cloud Base URL:[/bold cyan] {base_url}"
)
client = Client(base_url=base_url, api_key=api_key)

# Import our F2 pipeline
from app.agents.graph import run_analysis_pipeline

# ── LLM-as-Judge setup (Arize Phoenix Evals + Gemini) ─────────────────────────
# The deterministic evaluator below (`wait_discipline`) only checks exact-match
# action == expected_action. That CANNOT tell whether the agent's *rationale* was
# grounded in the evidence it analyzed, or whether a WAIT was disciplined vs. a
# cop-out. For that we use Phoenix's LLM-as-a-judge evaluators, powered by Gemini.
#
# The Phoenix `google` adapter uses the google-genai SDK, which authenticates from
# the GOOGLE_API_KEY / GEMINI_API_KEY env var. Our .env stores the key as
# GOOGLE_API_KEY_1, so we mirror it into the names google-genai expects. Fail-soft:
# if no key or the evals package is unavailable, we skip LLM judges and still run
# the deterministic experiment.
_LLM_JUDGE = None
_judge_imports_ok = False
try:
    # This app authenticates to Gemini via Vertex AI (USE_VERTEX=true +
    # GOOGLE_CLOUD_PROJECT + ADC/service account) — the GOOGLE_API_KEY_1 in .env is
    # a placeholder. The Phoenix `google` adapter wraps the google-genai SDK, whose
    # default Client honours these env vars. So we mirror the app's auth mode:
    #   • Vertex path  → set GOOGLE_GENAI_USE_VERTEXAI=true + project/location
    #   • API-key path → only if a REAL key (starts with "AIza") is present
    _use_vertex = os.environ.get("USE_VERTEX", "false").lower() in ("true", "1", "t")
    _project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    _location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

    _raw_key = (
        os.environ.get("GOOGLE_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY_1")
        or ""
    )
    _real_key = (
        _raw_key if _raw_key.startswith("AIza") else ""
    )  # filter out placeholders

    _judge_auth_ok = False
    if _use_vertex and _project:
        # Route google-genai through Vertex (same auth as the main pipeline).
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", _project)
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", _location)
        _judge_auth_ok = True
        _auth_mode = f"Vertex AI (project={_project}, location={_location})"
    elif _real_key:
        os.environ.setdefault("GOOGLE_API_KEY", _real_key)
        os.environ.setdefault("GEMINI_API_KEY", _real_key)
        _judge_auth_ok = True
        _auth_mode = "Generative Language API key"
    else:
        _auth_mode = "none"

    from phoenix.evals import LLM, create_classifier

    if _judge_auth_ok:
        # gemini-2.5-flash is fast + cheap and supports structured output, which the
        # Phoenix classifier requires. (Judges run off the critical path here.)
        _LLM_JUDGE = LLM(provider="google", model="gemini-2.5-flash")
        _judge_imports_ok = True
        console.print(
            f"[bold green]   [OK] LLM-as-Judge ready (Gemini via {_auth_mode}).[/bold green]"
        )
    else:
        console.print(
            "[yellow]   [WARN] No valid Gemini auth (set USE_VERTEX+GOOGLE_CLOUD_PROJECT, "
            "or a real GOOGLE_API_KEY) — skipping LLM judges (deterministic only).[/yellow]"
        )
except Exception as _e:
    console.print(
        f"[yellow]   [WARN] LLM-judge setup failed ({_e}) — deterministic only.[/yellow]"
    )

console.print("\n[bold cyan][Step 1] Creating/Fetching Dataset...[/bold cyan]")
# Dataset should include weak stocks that SHOULD produce WAIT (seed failures for before/after demo)
df = pd.DataFrame(
    [
        {
            "ticker": "YESBANK.NS",
            "expected_action": "WAIT",
            "reason": "Weak fundamentals and high dilution",
        },
        {
            "ticker": "IDEA.NS",
            "expected_action": "WAIT",
            "reason": "High debt, poor fundamentals",
        },
        {
            "ticker": "RELIANCE.NS",
            "expected_action": "BUY",
            "reason": "Strong large cap fundamentals",
        },
    ]
)

try:
    dataset = client.datasets.create_dataset(
        name="wait-discipline-stocks",
        dataframe=df,
        input_keys=["ticker"],
        output_keys=["expected_action", "reason"],
    )
    console.print(
        "   [bold green][OK] Created new dataset 'wait-discipline-stocks' in Phoenix Cloud![/bold green]"
    )
except Exception as err:
    console.print(
        f"   [dim]Dataset already exists or creation failed ({err}). Attempting to fetch existing...[/dim]"
    )
    # Fetch existing
    datasets = client.datasets.list()
    dataset = next(
        (
            d
            for d in datasets
            if getattr(d, "name", d.get("name", "")) == "wait-discipline-stocks"
        ),
        None,
    )
    if dataset:
        console.print(
            "   [bold green][OK] Using existing dataset 'wait-discipline-stocks' from Phoenix Cloud.[/bold green]"
        )
    else:
        console.print(
            "   [bold red][ERROR] Could not create or fetch dataset![/bold red]"
        )
        exit(1)


# Define the task function
def stock_task(input_data) -> dict:
    ticker = input_data["ticker"]

    action = "ERROR"
    rationale = ""
    evidence = ""
    confidence = 0
    try:
        res = run_analysis_pipeline(symbol=ticker, suggested_horizon="SHORT")
        final_rec = res.get("final_recommendation", {})
        action = final_rec.get("recommendation", "UNKNOWN")
        confidence = final_rec.get("confidence", 0)

        # rationale = what the agent SAID (its narrative + debate synthesis).
        rationale_parts = [
            final_rec.get("narrative", ""),
            final_rec.get("debate_summary", ""),
        ]
        rationale = "\n".join(p for p in rationale_parts if p).strip()

        # evidence = what the agent SAW (per-specialist signals + risks/catalysts +
        # macro). The LLM judge checks the rationale against THIS context — exactly
        # what exact-match cannot do.
        signals = final_rec.get("agent_signals", {})
        evidence = (
            f"Specialist signals: {signals}\n"
            f"Confidence: {confidence}% | Macro regime: {final_rec.get('macro_regime', 'N/A')} "
            f"| Market pulse: {final_rec.get('market_pulse_score', 'N/A')}\n"
            f"Key catalysts: {final_rec.get('key_catalysts', [])}\n"
            f"Key risks: {final_rec.get('key_risks', [])}\n"
            f"Validator status: {final_rec.get('validator_status', 'N/A')} "
            f"| issues: {final_rec.get('validator_issues', [])}"
        ).strip()
    except Exception as e:
        console.print(f"Error running pipeline for {ticker}: {e}")

    return {
        "action": action,
        "ticker": ticker,
        "rationale": rationale,
        "evidence": evidence,
        "confidence": confidence,
    }


# Define the custom evaluator (Plain function!)
def wait_discipline(output, expected) -> dict:
    action = output["action"]
    expected_action = expected["expected_action"]

    score = 1.0 if action == expected_action else 0.0
    label = "YES" if score == 1.0 else "NO"

    if score == 1.0:
        explanation = (
            f"Agent correctly output {action} matching expected {expected_action}."
        )
    else:
        explanation = f"Failed! Agent output {action} but expected {expected_action}."

    return {"score": score, "label": label, "explanation": explanation}


# ── LLM-as-Judge evaluators (Gemini via Phoenix Evals) ────────────────────────
# Each is built with create_classifier (structured-output classification) and then
# wrapped in a plain (output, expected) -> dict function so the Phoenix experiment
# runner can call it the same way as the deterministic evaluator above.


def _unwrap_score(scores):
    """Phoenix evaluators return List[Score]; take the first and normalise to the
    {score, label, explanation} dict the experiment runner expects."""
    s = scores[0] if isinstance(scores, list) and scores else scores
    return {
        "score": float(getattr(s, "score", 0.0) or 0.0),
        "label": getattr(s, "label", None) or "NA",
        "explanation": getattr(s, "explanation", "") or "",
    }


# Built lazily only if the LLM judge initialised. Each evaluator must be a *named*
# function so it shows up with a clean name in the Phoenix Cloud UI.
llm_evaluators = []
if _judge_imports_ok and _LLM_JUDGE is not None:
    # 1) GROUNDEDNESS — is the rationale supported by the evidence the agent saw?
    _grounded_clf = create_classifier(
        name="rationale_groundedness",
        llm=_LLM_JUDGE,
        prompt_template=(
            "You are auditing a stock-analysis agent. Decide whether its RATIONALE is "
            "fully supported by the EVIDENCE it analyzed. Mark 'hallucinated' if the "
            "rationale asserts facts, catalysts, or conviction NOT present in the evidence.\n\n"
            "[Action]: {action}\n"
            "[Rationale]: {rationale}\n\n"
            "[Evidence the agent saw]:\n{evidence}\n\n"
            "Is the rationale grounded in the evidence? Answer 'grounded' or 'hallucinated'."
        ),
        choices={"grounded": 1.0, "hallucinated": 0.0},
    )

    def rationale_groundedness(output) -> dict:
        if not output.get("rationale"):
            return {
                "score": 0.0,
                "label": "no_rationale",
                "explanation": "Agent produced no rationale to judge.",
            }
        return _unwrap_score(
            _grounded_clf.evaluate(
                {
                    "action": output.get("action", ""),
                    "rationale": output.get("rationale", ""),
                    "evidence": output.get("evidence", ""),
                }
            )
        )

    llm_evaluators.append(rationale_groundedness)

    # 2) DECISION CORRECTNESS — is the action reasonable given the evidence?
    #    (Tolerant LLM version of exact-match: BUY vs WAIT may both be defensible.)
    _correct_clf = create_classifier(
        name="decision_correctness",
        llm=_LLM_JUDGE,
        prompt_template=(
            "You are a senior portfolio manager reviewing an analysis agent. Given the "
            "EVIDENCE and the agent's ACTION, decide whether the action is a reasonable, "
            "defensible decision (it need not be the only valid one).\n\n"
            "[Action]: {action}\n"
            "[Confidence]: {confidence}%\n"
            "[Evidence]:\n{evidence}\n\n"
            "Is the action reasonable given the evidence? Answer 'reasonable' or 'unreasonable'."
        ),
        choices={"reasonable": 1.0, "unreasonable": 0.0},
    )

    def decision_correctness(output) -> dict:
        return _unwrap_score(
            _correct_clf.evaluate(
                {
                    "action": output.get("action", ""),
                    "confidence": output.get("confidence", 0),
                    "evidence": output.get("evidence", ""),
                }
            )
        )

    llm_evaluators.append(decision_correctness)

    # 3) WAIT-REFUSAL QUALITY — only meaningful when the agent chose WAIT. Judges
    #    whether WAIT was a disciplined, evidence-backed refusal vs. giving up.
    _refusal_clf = create_classifier(
        name="wait_refusal_quality",
        llm=_LLM_JUDGE,
        prompt_template=(
            "A stock-analysis agent output WAIT (declined to trade). Judge whether this "
            "was a DISCIPLINED refusal — a deliberate, evidence-backed choice to avoid a "
            "low-conviction trade — versus an unjustified cop-out with no supporting reason.\n\n"
            "[Rationale]: {rationale}\n"
            "[Evidence]:\n{evidence}\n\n"
            "Answer 'disciplined' or 'cop_out'."
        ),
        choices={"disciplined": 1.0, "cop_out": 0.0},
    )

    def wait_refusal_quality(output) -> dict:
        # Only score WAIT decisions; pass-through (1.0) for non-WAIT so the metric
        # isn't penalised on rows it doesn't apply to.
        if output.get("action") != "WAIT":
            return {
                "score": 1.0,
                "label": "n/a_not_wait",
                "explanation": "Action was not WAIT; refusal metric not applicable.",
            }
        return _unwrap_score(
            _refusal_clf.evaluate(
                {
                    "rationale": output.get("rationale", ""),
                    "evidence": output.get("evidence", ""),
                }
            )
        )

    llm_evaluators.append(wait_refusal_quality)


# Assemble the full evaluator list: deterministic exact-match + LLM judges.
all_evaluators = [wait_discipline] + llm_evaluators
console.print(
    f"\n[bold cyan][Step 2] Running Experiment 'wait-discipline-eval' "
    f"with {len(all_evaluators)} evaluators "
    f"({len(llm_evaluators)} LLM-as-judge)...[/bold cyan]"
)
try:
    experiment = client.experiments.run_experiment(
        dataset=dataset,
        task=stock_task,
        evaluators=all_evaluators,
        experiment_name="wait-discipline-eval",
    )

    console.print(
        "\n[bold green][SUCCESS] Experiment Completed successfully![/bold green]"
    )

    # Retrieve experiment URLs properly. The phoenix.client RanExperiment is a
    # TypedDict (keys: experiment_id, dataset_id) — NOT an object with .id/.dataset_id,
    # so the old attribute access always fell through to "default" and produced a
    # broken compare link (experimentId=default → generic Phoenix page). Read the
    # dict keys, but keep attribute access as a fallback for older client shapes.
    def _exp_field(exp, *names):
        for n in names:
            if isinstance(exp, dict) and exp.get(n):
                return exp[n]
            if hasattr(exp, n) and getattr(exp, n):
                return getattr(exp, n)
        return None

    dataset_id = _exp_field(experiment, "dataset_id")
    experiment_id = _exp_field(experiment, "experiment_id", "id")

    if not dataset_id:
        dataset_id = "default"
    if not experiment_id:
        experiment_id = "default"

    # Generate direct compare URL
    compare_url = (
        f"{base_url}/datasets/{dataset_id}/compare?experimentId={experiment_id}"
    )

    console.print(
        Panel(
            f"[bold cyan]>> Dataset Experiments Dashboard:[/bold cyan]\n"
            f"[underline blue]{base_url}/datasets/{dataset_id}/experiments[/underline blue]\n\n"
            f"[bold green]>> Direct Experiment Comparison View:[/bold green]\n"
            f"[underline blue]{compare_url}[/underline blue]\n",
            title="Phoenix Cloud Dashboard Links",
            border_style="magenta",
            expand=False,
        )
    )
except Exception as e:
    console.print(f"\n[bold red][ERROR] Failed to run experiment:[/bold red] {e}")
