"""
Vertex Agent Engine Application Wrapper for ArthaVest.
"""


class ArthaVestAgent:
    def set_up(self):
        # Runs ONCE in the cloud runtime, AFTER deploy. Build the compiled graph here.
        from app.core.observability import init_observability
        from app.agents.graph import build_analysis_graph

        init_observability()  # tracing on in the cloud too
        self.graph = build_analysis_graph()

    def query(self, symbol: str, suggested_horizon: str | None = None):
        # The callable the hosted endpoint exposes.
        from app.agents.graph import _get_default_state

        state = _get_default_state("analyze", symbol, suggested_horizon)
        result = self.graph.invoke(state)
        return result.get("final_recommendation", {})
