"""Explicit local identity and per-request database sessions."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.modules.knowledge.service import KnowledgeService


def get_actor(request: Request) -> str:
    """Local development identity; never trust a caller-supplied identity header."""
    return request.app.state.actor_id


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


def get_service(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> KnowledgeService:
    return KnowledgeService(session, request.app.state.storage_root, request.app.state.pipeline)


Actor = Annotated[str, Depends(get_actor)]
Service = Annotated[KnowledgeService, Depends(get_service)]
