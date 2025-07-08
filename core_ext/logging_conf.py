import logging
import sys

import structlog


def setup() -> None:
    """Configure structlog for JSON output to stdout."""
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(message)s")

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )


