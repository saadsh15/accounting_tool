from celery import shared_task
from celery.utils.log import get_task_logger

from .models import Statement
from .utils import process_statement

logger = get_task_logger(__name__)


@shared_task
def process_statement_task(statement_id):
    """Extracts transactions from an uploaded statement.

    Runs on a worker rather than in the request cycle: OCR plus per-transaction
    LLM calls can take minutes, far beyond the Gunicorn worker timeout.
    """
    statement = Statement.objects.filter(pk=statement_id).first()
    if statement is None:
        # The account (and its statements) can be deleted while the job is queued.
        logger.warning("Statement %s no longer exists; nothing to process.", statement_id)
        return 0

    # Make re-processing idempotent. Without this, re-running a job that already
    # created some transactions would duplicate them.
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
