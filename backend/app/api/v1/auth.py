from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import AnyUser, Session
from app.schemas.auth import ApprovalRequest, ApprovalToken, RefreshRequest, TokenPair, UserOut
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=TokenPair)
async def login(
    session: Session, form: Annotated[OAuth2PasswordRequestForm, Depends()]
) -> TokenPair:
    user = await auth_service.authenticate(session, form.username, form.password)
    return auth_service.issue_tokens(user)


@router.post("/refresh", response_model=TokenPair)
async def refresh(session: Session, body: RefreshRequest) -> TokenPair:
    return await auth_service.refresh(session, body.refresh_token)


@router.get("/me", response_model=UserOut)
async def me(user: AnyUser) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/approvals", response_model=ApprovalToken)
async def approve(session: Session, _: AnyUser, body: ApprovalRequest) -> ApprovalToken:
    """A pharmacist/admin enters their credentials to authorize a restricted
    action at the current terminal. Send the token as ``X-Approval-Token``."""
    return await auth_service.grant_approval(session, body.username, body.password)
