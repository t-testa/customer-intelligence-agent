from threading import Lock

from src.agents.agent import CustomerAgent
from src.agents.provider import DemoProvider, OpenAIProvider
from src.agents.sql_policy import SqlExecutor
from src.agents.tools import customer_tools
from src.config import ROOT
from src.retrieval.notes import DemoEmbedder, NotesIndex, OpenAIEmbedder
from src.services.insights import InsightService

_lock = Lock()


def get_runtime(app):
    """Build AI dependencies lazily, so basic health never needs model credentials/calls."""
    with _lock:
        if getattr(app.state, "runtime", None) is not None:
            return app.state.runtime
        settings = app.state.settings
        if settings.model_mode == "openai":
            from openai import OpenAI

            client = OpenAI(
                api_key=settings.openai_api_key.get_secret_value(),
                timeout=settings.model_timeout_seconds,
                max_retries=1,
            )
            provider = OpenAIProvider(client, settings.openai_model)
            embedder = OpenAIEmbedder(client, settings.embedding_model)
        else:
            provider, embedder = DemoProvider(), DemoEmbedder()
        notes = NotesIndex(
            ROOT / "data/customer_notes", embedder, app.state.metrics, ROOT / ".local/embeddings"
        )
        sql = SqlExecutor(
            settings.sql_database_url.get_secret_value() if settings.sql_database_url else None,
            app.state.metrics,
            settings.sql_max_rows,
            settings.sql_timeout_ms,
        )
        registry = customer_tools(
            app.state.customers, notes, sql, app.state.metrics, settings.today
        )
        runtime = {
            "agent": CustomerAgent(provider, registry, app.state.metrics, settings.max_tool_calls),
            "insights": InsightService(app.state.customers, notes, provider, settings.today),
            "registry": registry,
        }
        app.state.runtime = runtime
        return runtime
