"""Keep one bounded backend wake request off the Streamlit script thread."""

import logging
from concurrent.futures import Future
from threading import Thread
from time import monotonic, sleep

from frontend.api_client import (
    WAKE_CONNECT_TIMEOUT_SECONDS, WAKE_READ_TIMEOUT_SECONDS,
    ReadinessState, wake_backend_readiness,
)

logger = logging.getLogger("frontend.wake")


def launch_backend_wake(*, deadline: float, retry_interval: float) -> Future[ReadinessState]:
    """Retry /ready within one daemon worker until ready or the deadline."""
    result: Future[ReadinessState] = Future()

    def request() -> None:
        logger.warning("FRONTEND_WAKE_WORKER_STARTED")
        try:
            while True:
                remaining = deadline - monotonic()
                if remaining <= WAKE_CONNECT_TIMEOUT_SECONDS:
                    logger.warning("FRONTEND_WAKE_STARTUP_WINDOW_EXPIRED")
                    result.set_result("unavailable")
                    return
                read_timeout = min(WAKE_READ_TIMEOUT_SECONDS, remaining - WAKE_CONNECT_TIMEOUT_SECONDS)
                state = wake_backend_readiness(read_timeout=read_timeout)
                logger.warning("FRONTEND_WAKE_READY_STATUS=%s", state)
                if state != "starting":
                    result.set_result(state)
                    return
                remaining = deadline - monotonic()
                if remaining <= 0:
                    logger.warning("FRONTEND_WAKE_STARTUP_WINDOW_EXPIRED")
                    result.set_result("unavailable")
                    return
                sleep(min(retry_interval, remaining))
        except Exception as exc:
            logger.error("FRONTEND_WAKE_WORKER_EXCEPTION=%s", type(exc).__name__)
            result.set_result("unavailable")

    worker = Thread(target=request, name="backend-wake", daemon=True)
    logger.warning("FRONTEND_WAKE_WORKER_CREATED")
    worker.start()
    return result
