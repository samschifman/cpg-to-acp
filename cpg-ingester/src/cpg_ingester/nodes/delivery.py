"""Delivery Agent — sends assembled artifacts to acp-writer API."""

import logging

logger = logging.getLogger(__name__)


def delivery(state: dict) -> dict:
    logger.info("delivery: stub")
    return state
