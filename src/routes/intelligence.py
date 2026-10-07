from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from src.auth import Principal, authenticate, require_reviewer
from src.repositories.analytics import AnalyticsRepository
from src.repositories.intelligence import EventRepository
from src.services.intelligence import EventStatus, IntelligenceEvent
from src.services.trends import CustomerTrend, TrendService

router = APIRouter(tags=["intelligence"])


@router.get("/intelligence/trends", response_model=list[CustomerTrend])
def trends(
    request: Request, window_days: int = Query(7, ge=1, le=90), principal=Depends(authenticate)
):
    state = request.app.state
    return TrendService(state.customers, AnalyticsRepository(state.db), state.settings.today).all(
        window_days
    )


@router.get("/intelligence/events", response_model=list[IntelligenceEvent])
def events(
    request: Request,
    status: EventStatus | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    principal=Depends(authenticate),
):
    return EventRepository(request.app.state.db).list(status, limit, offset)


@router.post("/intelligence/events/{event_id}/acknowledge", response_model=IntelligenceEvent)
def acknowledge(event_id: UUID, request: Request, principal: Principal = Depends(authenticate)):
    require_reviewer(principal)
    return EventRepository(request.app.state.db).transition(
        event_id, EventStatus.ACKNOWLEDGED, principal.actor
    )


@router.post("/intelligence/events/{event_id}/resolve", response_model=IntelligenceEvent)
def resolve(event_id: UUID, request: Request, principal: Principal = Depends(authenticate)):
    require_reviewer(principal)
    return EventRepository(request.app.state.db).transition(
        event_id, EventStatus.RESOLVED, principal.actor
    )
