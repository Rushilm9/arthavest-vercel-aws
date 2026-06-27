"""
Phoenix Cloud MCP (Model Context Protocol) Client.
Handles JSON-RPC 2.0 communication over stdio with Node-based @arizeai/phoenix-mcp.
"""

from __future__ import annotations

import os
import json
import asyncio
import subprocess
from typing import Any
from rich.console import Console
from rich.panel import Panel

console = Console()


class PhoenixMCPError(RuntimeError):
    """Raised when the Arize Phoenix MCP server returns an error envelope."""

    pass


class PhoenixMCP:
    """
    Context manager for Arize Phoenix MCP communication.
    Spawns the Node process on __aenter__ and safely terminates it on __aexit__.
    """

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self._req_id = 0

    async def __aenter__(self) -> "PhoenixMCP":
        api_key = os.environ.get("PHOENIX_API_KEY")
        endpoint = os.environ.get(
            "PHOENIX_COLLECTOR_ENDPOINT", "https://app.phoenix.arize.com"
        )

        if not api_key:
            raise RuntimeError(
                "PHOENIX_API_KEY environment variable is required but missing."
            )

        # Derive base URL from the collector endpoint to ensure workspace slug is included
        base_url = "https://app.phoenix.arize.com"
        if "localhost" in endpoint:
            base_url = "http://localhost:6006"
        elif "/v1/traces" in endpoint:
            base_url = endpoint.split("/v1/traces")[0]

        env = {
            **os.environ,
            "PHOENIX_CLIENT_HEADERS": f"authorization={api_key}",
            "PHOENIX_BASE_URL": base_url,
        }

        # Validate that npx is installed in the system PATH
        is_windows = os.name == "nt"
        npx_cmd = "npx.cmd" if is_windows else "npx"

        # Pre-test command presence
        try:
            subprocess.run(
                [npx_cmd, "--version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=is_windows,
                check=True,
            )
        except Exception:
            console.print(
                Panel.fit(
                    "[bold red]❌ ERROR: 'npx' is not found in your system PATH![/bold red]\n"
                    "Please install Node.js from [underline]https://nodejs.org/[/underline] to resolve this.",
                    title="Prerequisite Failure",
                )
            )
            raise RuntimeError("Node.js / npx is not installed or not in PATH.")

        # Using @latest and passing base URL and api key explicitly
        cmd = [
            npx_cmd,
            "-y",
            "@arizeai/phoenix-mcp@latest",
            "--baseUrl",
            base_url,
            "--apiKey",
            api_key,
        ]

        console.print(
            f"[bold blue]⚡ [MCP] Spawning Phoenix MCP subprocess:[/bold blue] [cyan]{' '.join(cmd)}[/cyan]"
        )

        # Redirecting stderr to a file prevents pipeline hanging on Windows
        self._stderr_file = open("mcp_stderr.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr_file,
            text=True,
            encoding="utf-8",
            env=env,
            bufsize=1,  # Line-buffered
            shell=is_windows,
        )

        # Handshake step 1: Send initialize request
        try:
            init_res = await self._send(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "arthavest-phoenix-mcp", "version": "1.0.0"},
                },
            )
        except Exception as e:
            console.print(f"[bold red]❌ [MCP] Handshake failed: {e}[/bold red]")
            raise e

        # Handshake step 2: Send initialized notification
        await self._send_notification("notifications/initialized", {})
        console.print(
            "[bold green]✅ [MCP] Handshake completed successfully![/bold green]"
        )

        return self

    async def __aexit__(self, *exc) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()

        if hasattr(self, "_stderr_file") and self._stderr_file:
            self._stderr_file.close()

    async def _send(self, method: str, params: dict[str, Any]) -> dict:
        """Sends a JSON-RPC request and waits for the matching response."""
        if not self.proc or not self.proc.stdin or not self.proc.stdout:
            raise RuntimeError("MCP subprocess is not running.")

        self._req_id += 1
        req = {
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": method,
            "params": params,
        }

        req_str = json.dumps(req)
        self.proc.stdin.write(req_str + "\n")
        self.proc.stdin.flush()

        # Read line asynchronously using executor thread to avoid blocking loop
        line = await asyncio.to_thread(self.proc.stdout.readline)
        if not line:
            raise PhoenixMCPError("Phoenix MCP server closed pipe unexpectedly.")

        resp = json.loads(line)
        if "error" in resp:
            raise PhoenixMCPError(f"MCP server returned error: {resp['error']}")

        return resp.get("result", {})

    async def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Sends a JSON-RPC notification (no ID, no response expected)."""
        if not self.proc or not self.proc.stdin:
            raise RuntimeError("MCP subprocess is not running.")

        req = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        req_str = json.dumps(req)
        self.proc.stdin.write(req_str + "\n")
        self.proc.stdin.flush()

    async def call_tool(self, name: str, arguments: dict) -> Any:
        """Invoke an MCP tool by name and return its result content."""
        result = await self._send(
            "tools/call",
            {
                "name": name,
                "arguments": arguments,
            },
        )

        # Check if the MCP server returned a tool execution error
        if isinstance(result, dict) and result.get("isError"):
            content = result.get("content", [])
            err_msg = (
                content[0].get("text", "Unknown MCP tool error")
                if content
                else "Unknown MCP tool error"
            )
            raise PhoenixMCPError(f"MCP tool '{name}' failed: {err_msg}")

        content = result.get("content", [])
        if content and content[0].get("type") == "text":
            text_val = content[0]["text"]

            try:
                return json.loads(text_val)
            except json.JSONDecodeError:
                return text_val
        return result

    # ── High Level Convenience Methods ──────────────────────────────────────────

    async def list_projects(self) -> list[dict]:
        """List all Phoenix projects."""
        return await self.call_tool("list-projects", {})

    async def get_spans(
        self,
        *,
        project: str,
        limit: int = 50,
    ) -> dict:
        """Fetch spans matching a specific query/filter."""
        args: dict = {
            "project_identifier": project,
            "limit": limit,
            "include_annotations": True,
        }
        # Span indexing is async, do not rely on immediate get-spans
        return await self.call_tool("get-spans", args)

    async def get_prompt(self, *, name: str, version: str | None = None) -> dict:
        """Get a system prompt template by name and optional version."""
        args = {"prompt_identifier": name}
        if version:
            args["tag"] = version

        res = await self.call_tool("get-prompt", args)
        if isinstance(res, str):
            if "fetch failed" in res:
                return {}
            try:
                res = json.loads(res)
            except Exception:
                return {}

        if not isinstance(res, dict):
            return {}

        version_obj = res
        if "template" in version_obj:
            template = version_obj["template"]
            if isinstance(template, dict):
                if "messages" in template and isinstance(template["messages"], list):
                    msgs = template["messages"]
                    if msgs:
                        content = ""
                        for msg in msgs:
                            if isinstance(msg, dict) and msg.get("content"):
                                val = msg["content"]
                                if isinstance(val, list):
                                    for part in val:
                                        if isinstance(part, dict) and part.get("text"):
                                            content += part["text"] + "\n"
                                        elif isinstance(part, str):
                                            content += part + "\n"
                                elif isinstance(val, str):
                                    content += val + "\n"
                        version_obj["template"] = content.strip()
                elif "type" in template and template.get("type") == "text":
                    version_obj["template"] = template.get("content", "")

        return version_obj

    async def create_prompt(
        self,
        *,
        name: str,
        template: str,
        description: str,
        version_tag: str | None = None,
        model_provider: str = "GOOGLE",
        model_name: str | None = None,
    ) -> dict:
        """Commit a new prompt version to Phoenix Prompts."""
        actual_model = model_name or os.environ.get(
            "LLM_MODEL_NAME", "gemini-3.1-flash-lite"
        )

        args = {
            "name": name,
            "template": template,
            "description": description,
            "model_provider": model_provider,
            "model_name": actual_model,
        }

        await self.call_tool("upsert-prompt", args)

        # Tag the newly created prompt version if version_tag is specified
        if version_tag:
            try:
                versions_res = await self.call_tool(
                    "list-prompt-versions", {"prompt_identifier": name}
                )
                if isinstance(versions_res, str):
                    versions_res = json.loads(versions_res)

                versions = []
                if isinstance(versions_res, dict):
                    versions = versions_res.get("data", [])
                elif isinstance(versions_res, list):
                    versions = versions_res

                if versions:
                    newest_version_id = versions[0].get("id")
                    if newest_version_id:
                        await self.call_tool(
                            "add-prompt-version-tag",
                            {
                                "prompt_version_id": newest_version_id,
                                "name": version_tag,  # Use "name" for the tag label
                            },
                        )
                        console.print(
                            f"   [bold green]🏷️ Tagged version {newest_version_id} with tag '{version_tag}'[/bold green]"
                        )
            except Exception as tag_err:
                console.print(
                    f"   [bold yellow]⚠️ Failed to tag prompt version: {tag_err}[/bold yellow]"
                )

        return {"status": "success"}

    async def add_prompt_tag(
        self, prompt_name: str, version_tag: str, version_id: str = None
    ) -> dict:
        """Add a tag to a specific prompt version."""
        try:
            if not version_id:
                versions_res = await self.call_tool(
                    "list-prompt-versions", {"prompt_identifier": prompt_name}
                )
                if isinstance(versions_res, str):
                    versions_res = json.loads(versions_res)
                versions = []
                if isinstance(versions_res, dict):
                    versions = versions_res.get("data", [])
                elif isinstance(versions_res, list):
                    versions = versions_res

                if versions:
                    version_id = versions[0].get("id")

            if version_id:
                await self.call_tool(
                    "add-prompt-version-tag",
                    {"prompt_version_id": version_id, "name": version_tag},
                )
                return {"status": "success"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
        return {"status": "error", "message": "No version found to tag"}

    async def get_experiment_metrics(self) -> dict:
        # Dummy method to get metrics
        # For full implementation, one would query experiments endpoint via API, not just MCP
        return {"status": "success", "metrics": "Metrics fetch successful"}

    # ── LLM-as-Judge eval read-back (MCP) ───────────────────────────────────────
    # The judges THEMSELVES run locally in eval/run_experiment.py (phoenix.evals is
    # the only execution path — MCP cannot run a classifier). Those runs WRITE their
    # scores to Phoenix Cloud. This method READS them back over MCP so the frontend
    # can render them — the same MCP connection the self-improve loop already uses.

    async def _find_dataset_id(self, dataset_name: str) -> str | None:
        """Resolve a dataset name → Phoenix dataset id via MCP."""
        res = await self.call_tool("list-datasets", {})
        items = res.get("data", res) if isinstance(res, dict) else res
        for d in items or []:
            if isinstance(d, dict) and d.get("name") == dataset_name:
                return d.get("id")
        return None

    async def get_latest_experiment_evals(
        self,
        *,
        dataset_name: str = "wait-discipline-stocks",
    ) -> dict:
        """Fetch the most recent experiment's per-stock evaluator results via MCP.

        Returns a frontend-friendly dict:
            {
              "experiment_id": str,
              "dataset_name": str,
              "evaluators": ["wait_discipline", "rationale_groundedness", ...],
              "rows": [
                 {"ticker", "action", "expected_action", "trace_id",
                  "evals": {<evaluator_name>: {"label", "score", "explanation"}}},
                 ...
              ]
            }
        Fail-soft: returns {"rows": [], "error": ...} rather than raising.
        """
        try:
            dataset_id = await self._find_dataset_id(dataset_name)
            if not dataset_id:
                return {
                    "rows": [],
                    "evaluators": [],
                    "error": f"Dataset '{dataset_name}' not found.",
                }

            exps = await self.call_tool(
                "list-experiments-for-dataset", {"dataset_id": dataset_id}
            )
            exp_items = exps.get("data", exps) if isinstance(exps, dict) else exps
            if not exp_items:
                return {
                    "rows": [],
                    "evaluators": [],
                    "error": "No experiments yet. Run eval/run_experiment.py first.",
                }

            # Newest first (created_at desc); list-experiments returns newest-first already,
            # but sort defensively so we always show the latest run.
            exp_items = sorted(
                exp_items,
                key=lambda e: e.get("created_at", "") if isinstance(e, dict) else "",
                reverse=True,
            )
            latest = exp_items[0]
            exp_id = latest.get("id")

            detail = await self.call_tool(
                "get-experiment-by-id", {"experiment_id": exp_id}
            )
            results = (
                detail.get("experimentResult", []) if isinstance(detail, dict) else []
            )

            evaluator_names: list[str] = []
            rows: list[dict] = []
            for r in results:
                evals: dict = {}
                for ann in r.get("annotations") or []:
                    nm = ann.get("name")
                    if not nm:
                        continue
                    if nm not in evaluator_names:
                        evaluator_names.append(nm)
                    evals[nm] = {
                        "label": ann.get("label"),
                        "score": ann.get("score"),
                        "explanation": ann.get("explanation") or "",
                    }
                rows.append(
                    {
                        "ticker": (r.get("input") or {}).get("ticker", "?"),
                        "action": (r.get("output") or {}).get("action", "?"),
                        "expected_action": (r.get("reference_output") or {}).get(
                            "expected_action", "?"
                        ),
                        "trace_id": r.get("trace_id"),
                        "latency_ms": r.get("latency_ms"),
                        "evals": evals,
                    }
                )

            return {
                "experiment_id": exp_id,
                "dataset_name": dataset_name,
                "evaluators": evaluator_names,
                "rows": rows,
            }
        except Exception as e:
            return {"rows": [], "evaluators": [], "error": str(e)}
