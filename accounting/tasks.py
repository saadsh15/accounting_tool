import logging

from .models import Statement
from .utils import process_statement

logger = logging.getLogger(__name__)


def process_statement_job(statement_id):
    """Extracts transactions from an uploaded statement.

    Called from the QStash webhook (a separate serverless invocation), or inline
    when no queue is configured. Plain function, no broker: the whole point of the
    HTTP queue is that this runs in an ordinary request.
    """
    statement = Statement.objects.filter(pk=statement_id).first()
    if statement is None:
        # The account (and its statements) can be deleted while the job is queued.
        logger.warning("Statement %s no longer exists; nothing to process.", statement_id)
        return 0

    # Make re-processing idempotent. QStash retries on failure, and without this a
    # retry of a job that already created some transactions would duplicate them.
    statement.transactions.all().delete()

    Statement.objects.filter(pk=statement_id).update(
        status=Statement.Status.PROCESSING,
        error_message='',
        transactions_found=0,
    )

    try:
        count = process_statement(statement)
    except Exception as exc:
        logger.exception("Processing failed for statement %s", statement_id)
        Statement.objects.filter(pk=statement_id).update(
            status=Statement.Status.FAILED,
            error_message=str(exc)[:500],
        )
        raise

    Statement.objects.filter(pk=statement_id).update(
        status=Statement.Status.DONE,
        transactions_found=count,
    )
    return count
