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
        logger.warning("WAKE_REQUEST_STARTED")
        try:
            result.set_result(check_backend_health(read_timeout=read_timeout))
        except Exception:
            logger.warning("WAKE_REQUEST_CONNECTION_ERROR")
            result.set_result("starting")

    Thread(target=request, name="backend-wake", daemon=True).start()
    return result
