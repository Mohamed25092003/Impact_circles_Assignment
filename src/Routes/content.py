import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from Controllers import content as controller
from Helpers.database import get_db
from Models.content_schema import ApprovalInput, ContentEdit, ContentInput, ContentResponse, ContentStatus, MockPost

router = APIRouter(tags=['Part 2 — content'])
DB = Annotated[Session, Depends(get_db)]
reviewer_token = APIKeyHeader(name='X-Reviewer-Token', auto_error=False)


@router.post('/api/content/', response_model=ContentResponse, status_code=201)
def create_content(data: ContentInput, db: DB):
    return controller.create_content(data, db)


@router.post('/api/content/{content_id}/generate/', response_model=ContentResponse)
def generate_content(content_id: uuid.UUID, db: DB):
    return controller.generate_content(content_id, db)


@router.get('/api/content/{content_id}/', response_model=ContentResponse)
def get_content(content_id: uuid.UUID, db: DB):
    return controller.get_content(content_id, db)


@router.put('/api/content/{content_id}/', response_model=ContentResponse)
def edit_content(content_id: uuid.UUID, data: ContentEdit, db: DB):
    return controller.edit_content(content_id, data, db)


@router.post('/api/content/{content_id}/approve/', response_model=ContentResponse)
def approve_content(content_id: uuid.UUID, data: ApprovalInput, db: DB, token: str | None = Depends(reviewer_token)):
    controller.authorize_reviewer(token)
    return controller.approve_content(content_id, data, db)


@router.post('/api/content/{content_id}/publish/', response_model=ContentStatus)
def publish_content(content_id: uuid.UUID, db: DB, token: str | None = Depends(reviewer_token)):
    controller.authorize_reviewer(token)
    return controller.publish_content(content_id, db)


@router.get('/api/content/{content_id}/status/', response_model=ContentStatus)
def content_status(content_id: uuid.UUID, db: DB):
    return controller.get_status(content_id, db)


@router.post('/api/mock-publisher/{publication_id}/', tags=['local mock publisher'])
def mock_publish(publication_id: uuid.UUID, data: MockPost, db: DB, token: str | None = Depends(reviewer_token)):
    controller.authorize_reviewer(token)
    return controller.receive_mock_post(publication_id, data, db)


@router.get('/api/mock-publisher/{publication_id}/', response_class=HTMLResponse, tags=['local mock publisher'])
def mock_post(publication_id: uuid.UUID, db: DB):
    return controller.read_mock_post(publication_id, db)
