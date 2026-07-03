"""
zendesk_client.py — Fetch articles from OptiSigns Help Center via Zendesk API.
Public endpoint, no auth required.
"""

import requests
import logging
from typing import Generator

logger = logging.getLogger(__name__)

ZENDESK_BASE = "https://support.optisigns.com/api/v2/help_center"
LOCALE = "en-us"


def iter_articles(per_page: int = 100) -> Generator[dict, None, None]:
    """
    Paginate through all published articles in the Help Center.
    Yields raw article dicts from Zendesk API.
    """
    url = f"{ZENDESK_BASE}/{LOCALE}/articles.json"
    params = {"per_page": per_page, "sort_by": "updated_at", "sort_order": "desc"}

    page = 1
    total = 0

    while url:
        logger.info(f"Fetching page {page} — {url}")
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        articles = data.get("articles", [])
        total += len(articles)
        logger.info(f"  Got {len(articles)} articles (total so far: {total})")

        for article in articles:
            yield article

        # Pagination: Zendesk returns next_page as a full URL
        url = data.get("next_page")
        params = {}  # params are already encoded in next_page URL
        page += 1


def fetch_all_articles() -> list[dict]:
    """Return a flat list of all articles."""
    articles = list(iter_articles())
    logger.info(f"Total articles fetched: {len(articles)}")
    return articles


def fetch_categories() -> list[dict]:
    """Fetch all help center categories (for context/logging only)."""
    url = f"{ZENDESK_BASE}/{LOCALE}/categories.json"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json().get("categories", [])
