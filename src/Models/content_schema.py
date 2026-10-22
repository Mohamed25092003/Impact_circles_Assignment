import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContentType(str, Enum):
    DESCRIPTION = 'project_description'
    UPDATE = 'project_update'
    FINDINGS = 'research_findings'
    EVENT = 'event_announcement'


class PublishingChannel(str, Enum):
    LINKEDIN = 'linkedin'
    WEBSITE = 'website'


class InputModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class ContentInput(InputModel):
    project_name: str = Field(min_length=1, max_length=255)
    content_type: ContentType
    description: str = Field(min_length=10, max_length=12000)


class WebsiteDraft(InputModel):
    title: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=10, max_length=9000)


class GeneratedContent(InputModel):
    linkedin: str = Field(min_length=10, max_length=2800)
    newsletter: str = Field(min_length=10, max_length=3000)
    website: WebsiteDraft


class ContentEdit(InputModel):
    revision: int = Field(ge=1, description='Current revision returned by GET; prevents stale edits.')
    linkedin: str | None = Field(default=None, min_length=10, max_length=2800)
    newsletter: str | None = Field(default=None, min_length=10, max_length=3000)
    website: WebsiteDraft | None = None

    @model_validator(mode='after')
    def require_edit(self):
        if self.linkedin is None and self.newsletter is None and self.website is None:
            raise ValueError('Provide at least one generated output to edit.')
        return self


class ApprovalInput(InputModel):
    revision: int = Field(ge=1, description='Exact revision the reviewer has read.')
    approved: bool
    channels: list[PublishingChannel] = Field(default_factory=list, max_length=2)

    @model_validator(mode='after')
    def validate_channels(self):
        if self.approved and not self.channels:
            raise ValueError('Select at least one publishing channel when approving.')
        if len(set(self.channels)) != len(self.channels):
            raise ValueError('Channels must be unique.')
        return self


class ContentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_name: str
    content_type: ContentType
    description: str
    generated: GeneratedContent | None
    revision: int
    approved: bool
    channels: list[PublishingChannel]
    status: str
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PublicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    channel: PublishingChannel
    revision: int
    status: str
    external_id: str | None
    published_url: str | None
    published_at: datetime | None
    error: str | None
    attempts: list[dict]


class ContentStatus(BaseModel):
    id: uuid.UUID
    revision: int
    approved: bool
    channels: list[PublishingChannel]
    status: str
    publications: list[PublicationResponse]


class MockPost(InputModel):
    title: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=10, max_length=9000)
