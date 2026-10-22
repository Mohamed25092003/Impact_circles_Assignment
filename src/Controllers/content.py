import copy
import hashlib
import html
import json
import secrets
import uuid
from datetime import timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from fastapi import HTTPException
from groq import Groq, APIError, AuthenticationError, RateLimitError
from pydantic import ValidationError
from sqlalchemy import select

from Models import content_constants as config
from Models.content import ContentRecord, PublicationLog, utc_now
from Models.content_schema import GeneratedContent, ContentStatus, PublicationResponse


class PublisherRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the reviewer credential to a redirected destination.
        return None


def authorize_reviewer(token):
    if not config.REVIEWER_TOKEN:
        raise HTTPException(503, 'Set CONTENT_REVIEWER_TOKEN in .env.')
    if not token or not secrets.compare_digest(token, config.REVIEWER_TOKEN):
        raise HTTPException(403, 'A valid reviewer token is required.')


def get_content(content_id, db, lock=False):
    query = select(ContentRecord).where(ContentRecord.id == content_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    record = db.scalar(query)
    if not record:
        raise HTTPException(404, 'Content not found.')
    return record


def ensure_editable(record, db):
    if db.scalar(select(PublicationLog.id).where(PublicationLog.content_id == record.id, PublicationLog.status == 'publishing').limit(1)):
        raise HTTPException(409, 'Publishing is in progress. Finish or retry it before editing or changing approval.')


def content_digest(record):
    return hashlib.sha256(json.dumps({'revision': record.revision, 'generated': record.generated,
        'channels': sorted(record.channels)}, sort_keys=True).encode()).hexdigest()


def invalidate_approval(record):
    record.approved = False
    record.approved_revision = None
    record.approved_digest = None
    record.reviewed_at = None
    record.status, record.updated_at = 'draft', utc_now()
    record.revision += 1


def create_content(data, db):
    record = ContentRecord(project_name=data.project_name, content_type=data.content_type.value, description=data.description)
    db.add(record)
    db.commit()
    return record


def ai_schema():
    schema = GeneratedContent.model_json_schema()
    definitions = schema.get('$defs', {})
    def inline(value):
        if isinstance(value, list):
            return [inline(item) for item in value]
        if not isinstance(value, dict):
            return value
        if '$ref' in value:
            return inline(copy.deepcopy(definitions[value['$ref'].split('/')[-1]]))
        return {key: inline(item) for key, item in value.items() if key not in ('$defs', 'minLength', 'maxLength')}
    return inline(schema)


def generate_text(record):
    if not config.GROQ_API_KEY or config.GROQ_API_KEY.startswith('your_'):
        raise HTTPException(503, 'Configure GROQ_API_KEY in .env.')
    try:
        with Groq(api_key=config.GROQ_API_KEY, timeout=60, max_retries=0) as client:
            response = client.chat.completions.create(model=config.GROQ_MODEL, reasoning_effort='low', temperature=0.2,
                max_completion_tokens=5000,
                messages=[{'role': 'system', 'content': config.CONTENT_PROMPT},
                    {'role': 'user', 'content': json.dumps({'project_name': record.project_name,
                        'content_type': record.content_type, 'description': record.description})}],
                response_format={'type': 'json_schema', 'json_schema': {'name': 'research_content', 'strict': True, 'schema': ai_schema()}})
        if not response.choices or response.choices[0].finish_reason != 'stop':
            raise HTTPException(502, 'AI output was incomplete. No generated content was saved.')
        return GeneratedContent.model_validate_json(response.choices[0].message.content or '').model_dump(mode='json')
    except AuthenticationError as exc:
        raise HTTPException(503, 'The configured AI key was rejected.') from exc
    except RateLimitError as exc:
        raise HTTPException(429, 'AI rate limit reached. Retry later.') from exc
    except APIError as exc:
        raise HTTPException(503, 'AI generation is unavailable or timed out.') from exc
    except (ValidationError, ValueError, TypeError) as exc:
        raise HTTPException(502, 'AI returned invalid content. Nothing was overwritten.') from exc


def generate_content(content_id, db):
    record = get_content(content_id, db, lock=True)
    ensure_editable(record, db)
    generated = generate_text(record)
    record.generated = generated
    invalidate_approval(record)
    db.commit()
    return record


def edit_content(content_id, data, db):
    record = get_content(content_id, db, lock=True)
    ensure_editable(record, db)
    if not record.generated:
        raise HTTPException(409, 'Generate content before editing.')
    if data.revision != record.revision:
        raise HTTPException(409, 'Content changed. Read the latest revision first.')
    generated = {**record.generated, **data.model_dump(mode='json', exclude={'revision'}, exclude_none=True)}
    generated = GeneratedContent.model_validate(generated).model_dump(mode='json')
    if generated != record.generated:
        record.generated = generated
        invalidate_approval(record)
        db.commit()
    return record


def approve_content(content_id, data, db):
    record = get_content(content_id, db, lock=True)
    ensure_editable(record, db)
    if not record.generated:
        raise HTTPException(409, 'Generate content before reviewing it.')
    if data.revision != record.revision:
        raise HTTPException(409, 'Content changed. Review the latest revision before approval.')
    record.channels = sorted(channel.value for channel in data.channels) if data.approved else []
    record.approved, record.reviewed_at, record.updated_at = data.approved, utc_now(), utc_now()
    record.approved_revision = record.revision if data.approved else None
    record.approved_digest = content_digest(record) if data.approved else None
    record.status = 'approved' if data.approved else 'rejected'
    db.commit()
    return record


def get_status(content_id, db):
    record = get_content(content_id, db)
    logs = list(db.scalars(select(PublicationLog).where(PublicationLog.content_id == content_id,
        PublicationLog.revision == record.revision, PublicationLog.channel.in_(record.channels)).order_by(PublicationLog.channel)))
    return ContentStatus(id=record.id, revision=record.revision, approved=record.approved,
        channels=record.channels, status=record.status, publications=[PublicationResponse.model_validate(log) for log in logs])


def deliver(log_id, payload):
    target = urlsplit(config.PUBLISH_URL)
    if target.scheme not in ('http', 'https') or target.hostname not in ('localhost', '127.0.0.1', '::1'):
        return None, 'The mock publisher must use a local address.'
    request = Request(config.PUBLISH_URL + '/' + str(log_id) + '/', data=json.dumps(payload).encode(), method='POST',
        headers={'Content-Type': 'application/json', 'X-Reviewer-Token': config.REVIEWER_TOKEN})
    try:
        with build_opener(ProxyHandler({}), PublisherRedirectHandler()).open(request, timeout=config.HTTP_TIMEOUT) as response:
            data = json.load(response)
        if str(data['id']) != str(log_id) or data['url'] != config.PUBLIC_URL + '/api/mock-publisher/' + str(log_id) + '/':
            return None, 'Publishing API returned an invalid receipt.'
        return data, None
    except HTTPError as exc:
        return None, f'Publishing API returned HTTP {exc.code}.'
    except (URLError, TimeoutError, OSError):
        return None, 'Publishing API unavailable or timed out. Retrying will reuse the same post ID.'
    except (ValueError, TypeError, KeyError):
        return None, 'Publishing API returned an invalid receipt.'


def publish_content(content_id, db):
    record = get_content(content_id, db, lock=True)
    if not record.approved or record.approved_revision != record.revision or record.approved_digest != content_digest(record):
        raise HTTPException(409, 'The current content and channel selection need explicit reviewer approval.')
    revision = record.revision
    logs = []
    for channel in record.channels:
        log = db.scalar(select(PublicationLog).where(PublicationLog.content_id == content_id,
            PublicationLog.revision == revision, PublicationLog.channel == channel))
        if log is None:
            payload = record.generated['website'] if channel == 'website' else {'title': record.project_name, 'body': record.generated['linkedin']}
            log = PublicationLog(content_id=content_id, revision=revision, channel=channel, payload=payload, attempts=[])
            db.add(log)
        logs.append(log)
    if not logs:
        raise HTTPException(409, 'Select a publishing channel first.')
    for log in logs:
        if log.status == 'publishing' and log.started_at and (utc_now() - log.started_at.replace(tzinfo=timezone.utc)).total_seconds() < config.PUBLISH_LEASE_SECONDS:
            db.rollback()
            return get_status(content_id, db)
    operations = []
    for log in logs:
        if log.status == 'published':
            continue
        attempt_id = str(uuid.uuid4())
        log.status, log.started_at, log.error = 'publishing', utc_now(), None
        log.active_attempt = attempt_id
        log.attempts = log.attempts + [{'id': attempt_id, 'started_at': log.started_at.isoformat(), 'status': 'publishing', 'completed_at': None, 'error': None}]
        db.flush()
        operations.append((log.id, attempt_id, log.payload))
    record.status = 'publishing' if operations else 'published'
    db.commit()  # Save approval and delivery intents before the real HTTP requests.
    for log_id, attempt_id, payload in operations:
        receipt, error = deliver(log_id, payload)
        log = db.scalar(select(PublicationLog).where(PublicationLog.id == log_id).with_for_update().execution_options(populate_existing=True))
        attempts = copy.deepcopy(log.attempts)
        for attempt in attempts:
            if attempt['id'] == attempt_id:
                attempt.update(status='failed' if error else 'published', completed_at=utc_now().isoformat(), error=error)
        log.attempts = attempts
        if log.active_attempt == attempt_id:
            log.status, log.error = 'failed' if error else 'published', error
            if receipt:
                log.external_id, log.published_url, log.published_at = str(receipt['id']), receipt['url'], utc_now()
        db.commit()  # One failed channel never rolls back another channel's success.
    record = get_content(content_id, db, lock=True)
    if record.revision == revision:
        status = get_status(content_id, db)
        states = [log.status for log in status.publications]
        record.status = 'publishing' if 'publishing' in states else 'partially_published' if 'failed' in states and 'published' in states else 'failed' if 'failed' in states else 'published'
        db.commit()
    return get_status(content_id, db)


def receive_mock_post(log_id, data, db):
    log = db.scalar(select(PublicationLog).where(PublicationLog.id == log_id).with_for_update())
    if not log:
        raise HTTPException(404, 'Publication not found.')
    record = get_content(log.content_id, db)
    if not record.approved or record.approved_revision != log.revision or record.revision != log.revision or record.approved_digest != content_digest(record):
        raise HTTPException(409, 'This publication is not authorized by the current approval.')
    payload = data.model_dump(mode='json')
    if payload != log.payload or log.channel not in record.channels:
        raise HTTPException(409, 'Publication does not match the approved payload.')
    if log.mock_post is None:
        if log.status != 'publishing':
            raise HTTPException(409, 'This publication has not been initiated.')
        log.mock_post, log.mock_received_at = payload, utc_now()
        db.commit()
    return {'id': str(log.id), 'url': config.PUBLIC_URL + '/api/mock-publisher/' + str(log.id) + '/'}


def read_mock_post(log_id, db):
    log = db.get(PublicationLog, log_id)
    if not log or not log.mock_post:
        raise HTTPException(404, 'Published mock post not found.')
    return ('<!doctype html><html><head><meta charset="utf-8"><title>' + html.escape(log.mock_post['title']) +
        '</title></head><body><p>Local demo publication</p><h1>' + html.escape(log.mock_post['title']) +
        '</h1><main style="white-space:pre-wrap">' + html.escape(log.mock_post['body']) + '</main></body></html>')
