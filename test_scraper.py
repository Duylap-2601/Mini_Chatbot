"""
test_scraper.py — Quick smoke test for Part 1.
Run: python test_scraper.py
"""

import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

def main():
    logger.info("=== Testing Zendesk scraper ===")

    from scraper.zendesk_client import fetch_all_articles
    articles = fetch_all_articles()

    logger.info(f"\nTotal articles fetched: {len(articles)}")
    assert len(articles) >= 30, f"Expected ≥30 articles, got {len(articles)}"

    # Show sample
    sample = articles[0]
    logger.info(f"\nSample article:")
    logger.info(f"  id         : {sample.get('id')}")
    logger.info(f"  title      : {sample.get('title')}")
    logger.info(f"  slug       : {sample.get('slug')}")
    logger.info(f"  html_url   : {sample.get('html_url')}")
    logger.info(f"  updated_at : {sample.get('updated_at')}")
    logger.info(f"  body_len   : {len(sample.get('body') or '')} chars")

    logger.info("\n=== Testing Markdown converter ===")
    from scraper.markdown_converter import save_articles
    saved = save_articles(articles[:5], output_dir=Path("articles_test"))  # test on first 5

    logger.info(f"\nSaved {len(saved)} test files:")
    for s in saved:
        p = Path(s['path'])
        size_kb = p.stat().st_size / 1024
        logger.info(f"  {s['filename']:60s}  {size_kb:.1f} KB")

    # Show first file content preview
    first = Path(saved[0]['path'])
    content = first.read_text(encoding="utf-8")
    logger.info(f"\nPreview of '{saved[0]['filename']}':\n")
    logger.info(content[:600])

    logger.info("\n✅ Scraper test passed!")

if __name__ == "__main__":
    main()
