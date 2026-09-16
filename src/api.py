import re
from time import perf_counter
from uuid import uuid4

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from src.agents.agent import AgentAnswer, AskRequest
from src.auth import authenticate
from src.config import Settings
from src.database import Database
from src.errors import ConflictError, ModelError, NotFoundError, PolicyError
from src.models import Customer, Health, Risk, Summary
from src.observability.telemetry import Metrics, configure_logging, event, request_id
from src.repositories.customers import CustomerRepository
from src.runtime import get_runtime
from src.services.insights import CustomerInsight
from src.services.risk import calculate_risk


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging()
    app = FastAPI(
        title="Customer Intelligence Agent",
        version="0.1.0",
        description="Synthetic customer intelligence. MODEL_MODE=demo uses no external AI.",
    )
    app.state.settings = settings
    app.state.db = Database(settings.database_url.get_secret_value())
    app.state.metrics = Metrics()
    app.state.customers = CustomerRepository(app.state.db)

    @app.middleware("http")
    async def telemetry(request: Request, call_next):
        supplied = request.headers.get("X-Request-ID", "")
        rid = supplied if re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", supplied) else str(uuid4())
        token = request_id.set(rid)
        start = perf_counter()
        metrics = app.state.metrics
        metrics.increment("requests_total")
        try:
            try:
                response = await call_next(request)
            except Exception as exc:
                event("unhandled_error", error_type=type(exc).__name__)
                metrics.increment("errors_total")
                response = JSONResponse(
                    {"detail": "Internal service error", "request_id": rid}, status_code=500
                )
            response.headers["X-Request-ID"] = rid
            elapsed = (perf_counter() - start) * 1000
            metrics.increment("http_latency_ms_sum", elapsed)
            if response.status_code >= 400:
                metrics.increment("requests_failed")
            route = request.scope.get("route")
            event(
                "http_request",
                route=getattr(route, "path", "unmatched"),
                method=request.method,
                status=response.status_code,
                latency_ms=round(elapsed, 2),
            )
            return response
        finally:
            request_id.reset(token)

    error_map = [
        (NotFoundError, 404),
        (ConflictError, 409),
        (PolicyError, 422),
        (ModelError, 502),
        (psycopg.Error, 503),
    ]
    for error_type, status in error_map:

        def handler(request, exc, status=status):
            app.state.metrics.increment("errors_total")
            event("domain_error", status=status, error_type=type(exc).__name__)
            details = {
                404: "Entity not found",
                409: "State transition conflict",
                422: "Operation rejected by policy",
                502: "Model response unavailable or invalid",
                503: "Database unavailable",
            }
            return JSONResponse({"detail": details[status]}, status_code=status)

        app.add_exception_handler(error_type, handler)

    @app.get("/health", response_model=Health, tags=["operations"])
    def health():
        if not app.state.db.healthy():
            raise HTTPException(503, "PostgreSQL unavailable")
        return Health(status="ok", database="connected")

    secured = [Depends(authenticate)]

    @app.get("/metrics", response_model=dict[str, float], dependencies=secured, tags=["operations"])
    def metrics():
        return app.state.metrics.snapshot()

    @app.get("/customers/summary", response_model=Summary, dependencies=secured, tags=["customers"])
    def summary():
        return app.state.customers.get_summary()

    @app.get(
        "/customers/low-nps",
        response_model=list[Customer],
        dependencies=secured,
        tags=["customers"],
    )
    def low_nps(threshold: int = Query(30, ge=-100, le=100)):
        return app.state.customers.get_low_nps_customers(threshold)

    @app.get(
        "/customers/high-risk", response_model=list[Risk], dependencies=secured, tags=["customers"]
    )
    def high_risk():
        risks = [
            calculate_risk(c, settings.today()) for c in app.state.customers.get_all_customers()
        ]
        return [r for r in risks if r.risk_level == "HIGH"]

    @app.get(
        "/customers/{customer_id}",
        response_model=Customer,
        dependencies=secured,
        tags=["customers"],
    )
    def customer(customer_id: int):
        return app.state.customers.get_customer_by_id(customer_id)

    @app.get(
        "/customers/{customer_id}/risk",
        response_model=Risk,
        dependencies=secured,
        tags=["customers"],
    )
    def risk(customer_id: int):
        return calculate_risk(app.state.customers.get_customer_by_id(customer_id), settings.today())

    @app.post("/agent/ask", response_model=AgentAnswer, dependencies=secured, tags=["agent"])
    def ask(body: AskRequest):
        return get_runtime(app)["agent"].ask(body.question)

    @app.get(
        "/customers/{customer_id}/insight",
        response_model=CustomerInsight,
        dependencies=secured,
        tags=["agent"],
    )
    def insight(customer_id: int):
        return get_runtime(app)["insights"].get(customer_id)

    from src.routes.actions import router as action_router

    app.include_router(action_router)
    return app


app = create_app()
