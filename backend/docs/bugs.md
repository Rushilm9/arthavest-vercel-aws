# Codebase Audit: Vertex AI Integration, Legacy Cleanups, and Model Routing

This document details the audit of the codebase to verify compliance with the hackathon goals:
1. Exclusive use of Vertex AI (`ChatVertexAI`) when `USE_VERTEX=true` is enabled.
2. Complete removal/cleanup of Groq, Llama, round-robin, and old quota-tracking references.
3. Verification of correct `ModelTier` usage across all agent nodes.

---

## 1. Vertex AI Audit & Model Routing

### Findings:
* **Vertex AI Class Instantiation**: In `app/core/model_router.py`, `ChatVertexAI` is correctly imported and instantiated when `settings.USE_VERTEX` is set to `true` and the `langchain_google_vertexai` package is available (`_VERTEX_AVAILABLE = True`).
* **Fallback Vulnerability (Exclusivity Risk)**: If `settings.USE_VERTEX = true` but `_VERTEX_AVAILABLE` is `false` (e.g., due to a missing dependency during deployment), the model router silently falls back to `ChatGoogleGenerativeAI` (AI Studio). This violates the requirement of *exclusively* using Vertex AI when the flag is enabled.
* **Model ID Mappings (Architectural Discrepancy)**:
  In `app/core/model_router.py`, all model tiers are mapped to a single lower-tier model to reduce costs or rate-limits:
  * **Vertex Mode (`USE_VERTEX=true`)**:
    * All tiers (`FLASH_LITE`, `FLASH`, `PRO`, `PRO_THINK`) map to `"gemini-2.5-flash"`.
  * **AI Studio Mode (`USE_VERTEX=false`)**:
    * All tiers map to `"gemini-3.1-flash-lite"`.
  
  **Impact**: The `ModelTier.PRO_THINK` tier (used by the Debate agent) is intended to run on `gemini-2.5-pro` with active thinking capabilities. However, because it maps to `gemini-2.5-flash`, the thinking configuration conditional block is bypassed entirely:
  ```python
  kwargs_base: dict = {}
  if tier == ModelTier.PRO_THINK and "gemini-2.5-pro" in model_id:
      kwargs_base["model_kwargs"] = {
          "thinking_config": {"thinking_budget": 8192}
      }
  ```
  Since `"gemini-2.5-pro"` is not present in `"gemini-2.5-flash"`, the Debate agent is executed without its reasoning/thinking budget.

---

## 2. Legacy Cleanups Audit (Groq, Llama, Quota Tracking)

### Findings:
* **Active Code remnants**:
  * **`app/api/routes/analysis.py`** (lines 1769–1770): The test endpoint `POST /analysis/test-agent` still references and maps `GROQ_KEY_1` overrides to `settings.GROQ_API_KEY_1` (which does not exist in `config.py`):
    ```python
    elif req.custom_api_key == "GROQ_KEY_1":
        state["_custom_api_key"] = getattr(settings, "GROQ_API_KEY_1", None)
    ```
  * **`frontend/test_agent.html`** (lines 87–90, 103): The agent debugger HTML still contains select dropdown menu options referencing Groq, Llama, and Mixtral models, as well as the custom `GROQ_KEY_1` API key option.
* **Unused DB Schema remnants**:
  * **`app/db/models.py`** (lines 646–668): The database model `QuotaUsage` (table: `quota_usage`) is still defined here. The model comments still refer to `groq` and fallback paths. It is not imported or used anywhere in the active API or service layers.
* **Clean areas**:
  * `app/core/config.py` is completely clean of any Groq or Llama environment variable configuration requirements.
  * `.env.example` has been successfully updated and contains no reference to Groq or Llama api keys or settings.
  * `app/main.py` contains no quota tracking endpoints, middleware, or usage counters.

---

## 3. Agent Node Audit

All nodes in `app/agents/` were inspected for correct model tier selection and implementation.

| Agent / Node | File Path | Requested Tier | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Planner** | `app/agents/planner/node.py` | `ModelTier.PRO` | **OK** | Routes to `gemini-2.5-flash` under Vertex. |
| **Decision** | `app/agents/decision/node.py` | `ModelTier.PRO` | **OK** | Routes to `gemini-2.5-flash` under Vertex. |
| **Debate** | `app/agents/debate/node.py` | `ModelTier.PRO_THINK` | **NOT OK** | Routes to `gemini-2.5-flash` instead of `gemini-2.5-pro` under Vertex, skipping thinking config. |
| **Technical** | `app/agents/technical/node.py` | `ModelTier.FLASH` | **OK** | Routes to `gemini-2.5-flash` under Vertex. |
| **Fundamental** | `app/agents/fundamental/node.py` | `ModelTier.FLASH` | **OK** | Routes to `gemini-2.5-flash` under Vertex. |
| **Sentiment** | `app/agents/sentiment/node.py` | `ModelTier.FLASH` | **OK** | Routes to `gemini-2.5-flash` under Vertex. Falls back to offline `FinVADER` on failure. |
| **News** | `app/agents/news/node.py` | `ModelTier.FLASH` | **OK** | Routes to `gemini-2.5-flash` under Vertex. |
| **Economic** | `app/agents/economic/node.py` | `ModelTier.FLASH_LITE` | **OK** | Routes to `gemini-2.5-flash` under Vertex. |
| **Macro Context** | `app/agents/macro_context/node.py` | `ModelTier.PRO` | **OK** | Routes to `gemini-2.5-flash` under Vertex. |
| **Discovery** | `app/agents/discovery/node.py` | `ModelTier.FLASH` | **OK** | Routes to `gemini-2.5-flash` under Vertex. |
| **Chart Pattern** | `app/agents/chart_pattern/node.py` | `ModelTier.FLASH` | **OK** | Routes to `gemini-2.5-flash` under Vertex. |

---

## 4. Code Quality & Integration Recommendations

To ensure absolute compliance with the hackathon specifications, the following cleanups and adjustments are recommended:

### A. Disable Silent Fallbacks when `USE_VERTEX=true`
Modify `_make_chat` in `app/core/model_router.py` to raise a `RuntimeError` if Vertex AI is requested but the required dependency is not available.

```diff
def _make_chat(model_id: str, json_mode: bool, extra: dict | None = None):
     extra = extra or {}
-    if settings.USE_VERTEX and _VERTEX_AVAILABLE:
-        kwargs = {"model": model_id, "temperature": 0.0, "max_retries": 3,
-                  "project": settings.GOOGLE_CLOUD_PROJECT,
-                  "location": settings.GOOGLE_CLOUD_LOCATION, **extra}
-        if json_mode:
-            kwargs.setdefault("model_kwargs", {})["generation_config"] = {"response_mime_type": "application/json"}
-        return ChatVertexAI(**kwargs)
+    if settings.USE_VERTEX:
+        if not _VERTEX_AVAILABLE:
+            raise RuntimeError("Vertex AI requested (USE_VERTEX=true) but langchain_google_vertexai is not installed.")
+        kwargs = {
+            "model": model_id,
+            "temperature": 0.0,
+            "max_retries": 3,
+            "project": settings.GOOGLE_CLOUD_PROJECT,
+            "location": settings.GOOGLE_CLOUD_LOCATION,
+            **extra
+        }
+        if json_mode:
+            kwargs.setdefault("model_kwargs", {})["generation_config"] = {"response_mime_type": "application/json"}
+        return ChatVertexAI(**kwargs)
```

### B. Correct the Model ID Mapping for PRO and PRO_THINK
Ensure high-tier reasoning and synthesis nodes map to `gemini-2.5-pro` so thinking capabilities can be fully utilized.

```diff
 _VERTEX_MODEL_IDS: dict[ModelTier, str] = {
     ModelTier.FLASH_LITE: "gemini-2.5-flash",
     ModelTier.FLASH:      "gemini-2.5-flash",
-    ModelTier.PRO:        "gemini-2.5-flash",
-    ModelTier.PRO_THINK:  "gemini-2.5-flash",
+    ModelTier.PRO:        "gemini-2.5-pro",
+    ModelTier.PRO_THINK:  "gemini-2.5-pro",
 }
```

### C. Remove Remaining Groq References in Backend Router
Remove lines 1769–1770 from `app/api/routes/analysis.py`.

```diff
-        elif req.custom_api_key == "GROQ_KEY_1":
-            state["_custom_api_key"] = getattr(settings, "GROQ_API_KEY_1", None)
```

### D. Clean Up the Frontend Agent Debugger UI
Remove the select elements referencing Groq and Llama options in `frontend/test_agent.html`.
* Remove lines 87–90:
  ```html
  <option value="llama-3.3-70b-versatile">Llama 3.3 70B (via Groq)</option>
  <option value="llama-3.1-8b-instant">Llama 3.1 8B (via Groq)</option>
  <option value="mixtral-8x7b-32768">Mixtral 8x7B (via Groq)</option>
  <option value="gemma2-9b-it">Gemma 2 9B (via Groq)</option>
  ```
* Remove line 103:
  ```html
  <option value="GROQ_KEY_1">GROQ_API_KEY_1 (Groq 1)</option>
  ```
