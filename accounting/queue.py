"""HTTP job queue (Upstash QStash).

Serverless has no long-lived worker, so instead of a broker a job is *published*
to QStash, which then calls a webhook back into this app. That callback lands in a
fresh invocation, which is why the statement file has to live in object storage
rather than on local disk.

With no QSTASH_TOKEN configured the job runs inline, so development and tests need
no external service.
"""
import base64
import hashlib
import logging

import jwt
import requests
from django.conf import settings
from django.urls import reverse

logger = logging.getLogger(__name__)

PUBLISH_TIMEOUT = 10


def is_configured():
    return bool(getattr(settings, 'QSTASH_TOKEN', ''))


def _callback_url():
    return f"{settings.SITE_URL.rstrip('/')}{reverse('process_statement_webhook')}"


def enqueue_statement(statement_id):
    """Queues a statement for extraction. Returns True if it was handed to QStash,
    False if it was run inline (no queue configured)."""
    if not is_configured():
        # No queue: do the work now. Correct for local dev, and it keeps a
        # misconfigured deploy from silently dropping uploads on the floor.
        from .tasks import process_statement_job
        logger.info("QStash not configured; processing statement %s inline.", statement_id)
        process_statement_job(statement_id)
        return False

    response = requests.post(
        f"{settings.QSTASH_URL.rstrip('/')}/{_callback_url()}",
        headers={
            'Authorization': f"Bearer {settings.QSTASH_TOKEN}",
            'Content-Type': 'application/json',
            # Don't retry forever on a statement that will never parse.
            'Upstash-Retries': '2',
        },
        json={'statement_id': statement_id},
        timeout=PUBLISH_TIMEOUT,
    )
    response.raise_for_status()
    return True


def verify_signature(token, body, url):
    """Validates a QStash callback.

    The webhook is unauthenticated by nature -- anyone can POST to it -- so the
    signature is the only thing standing between the queue and an open endpoint
    that lets a stranger trigger work against arbitrary statement IDs.

    QStash signs a JWT (HS256) whose `body` claim is the base64url-encoded SHA-256
    of the raw request body, so a valid signature cannot be replayed against a
    different payload. It rotates keys, so both current and next are accepted.
    """
    keys = [
        getattr(settings, 'QSTASH_CURRENT_SIGNING_KEY', ''),
        getattr(settings, 'QSTASH_NEXT_SIGNING_KEY', ''),
    ]
    keys = [k for k in keys if k]
    if not keys:
        raise ValueError('No QStash signing keys configured; refusing to trust the callback.')

    expected_body_hash = base64.urlsafe_b64encode(hashlib.sha256(body).digest()).decode().rstrip('=')

    for key in keys:
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=['HS256'],
                issuer='Upstash',
                options={'require': ['exp', 'iss', 'sub']},
            )
        except jwt.PyJWTError:
            continue

        if claims.get('sub') != url:
            continue
        # Guards against a signature lifted from one request being replayed with
        # a different body.
        if claims.get('body', '').rstrip('=') != expected_body_hash:
            continue
        return True

    return False
