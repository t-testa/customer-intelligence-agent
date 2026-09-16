from uuid import UUID

from fastapi import APIRouter, Depends, Request

from src.auth import Principal, authenticate, require_reviewer
from src.repositories.actions import ActionRepository
from src.services.actions import Action, ActionService, ActionState

router = APIRouter(tags=["human approval"])


def service(request: Request):
    state = request.app.state
    return ActionService(
        ActionRepository(state.db), state.customers, state.metrics, state.settings.today
    )


@router.post("/customers/{customer_id}/actions/followup", response_model=Action, status_code=201)
def propose(customer_id: int, request: Request, principal: Principal = Depends(authenticate)):
    return service(request).propose_followup(customer_id, principal.actor)


@router.get("/actions/{action_id}", response_model=Action)
def get(action_id: UUID, request: Request, principal: Principal = Depends(authenticate)):
    return service(request).repository.get(action_id)


@router.get("/actions/{action_id}/audit")
def audit(action_id: UUID, request: Request, principal: Principal = Depends(authenticate)):
    return service(request).repository.audit(action_id)


@router.post("/actions/{action_id}/approve", response_model=Action)
def approve(action_id: UUID, request: Request, principal: Principal = Depends(authenticate)):
    require_reviewer(principal)
    return service(request).transition(action_id, ActionState.APPROVED, principal.actor)


@router.post("/actions/{action_id}/reject", response_model=Action)
def reject(action_id: UUID, request: Request, principal: Principal = Depends(authenticate)):
    require_reviewer(principal)
    return service(request).transition(action_id, ActionState.REJECTED, principal.actor)


@router.post("/actions/{action_id}/execute", response_model=Action)
def execute(action_id: UUID, request: Request, principal: Principal = Depends(authenticate)):
    require_reviewer(principal)
    return service(request).transition(action_id, ActionState.EXECUTED, principal.actor)
