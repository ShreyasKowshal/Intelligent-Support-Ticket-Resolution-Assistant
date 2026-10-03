"""Keep one bounded backend wake request off the Streamlit script thread."""

import logging
from concurrent.futures import Future
from threading import Thread

from frontend.api_client import HealthState, check_backend_health

logger = logging.getLogger("frontend.wake")


def launch_backend_wake(*, read_timeout: float) -> Future[HealthState]:
    """Start a daemon worker that never accesses Streamlit session state."""
    result: Future[HealthState] = Future()

    def request() -> None:
        logger.warning("FRONTEND_WAKE_WORKER_STARTED")
        try:
            result.set_result(check_backend_health(read_timeout=read_timeout))
        except Exception as exc:
            logger.error("FRONTEND_WAKE_WORKER_EXCEPTION=%s", type(exc).__name__)
            result.set_result("unavailable")

    worker = Thread(target=request, name="backend-wake", daemon=True)
    logger.warning("FRONTEND_WAKE_WORKER_CREATED")
    worker.start()
    return result
