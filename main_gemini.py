"""
main_gemini.py
~~~~~~~~~~~~~~
Daily sync orchestrator — Gemini version.

What this does:
  1. Scrape all articles from OptiSigns Help Center (Zendesk API)
  2. Convert to clean Markdown and save to articles/ directory
  3. Track delta (added / updated / unchanged) using SHA-256 hashing
  4. Log a summary report

Note: No cloud Vector Store upload needed with the Gemini approach.
      Articles are stored locally and loaded into Gemini's 1M context at query time.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Load environment before imports
load_dotenv()

# Setup logging
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
log_file = LOG_DIR / f"run_{timestamp}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# Imports from project
from scraper.zendesk_client import fetch_all_articles
from scraper.markdown_converter import save_articles
from vector_store.delta_tracker import DeltaTracker


def run_sync() -> None:
    start_time = datetime.now(timezone.utc)
    logger.info("OptiBot Gemini Sync Job started at %s", start_time.isoformat())
    logger.info("Log file: %s", log_file.resolve())

    # Check for GOOGLE_API_KEY
    if not os.getenv("GOOGLE_API_KEY"):
        logger.warning("[WARN] GOOGLE_API_KEY not found in environment. You will need it to query.")

    # ── Step 1: Scrape ──────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 1 — Scraping OptiSigns Help Center articles")
    logger.info("=" * 60)

    articles = fetch_all_articles()

    if len(articles) < 30:
        logger.warning("Only fetched %d articles — expected >=30!", len(articles))
    else:
        logger.info("Fetched %d articles [OK]", len(articles))

    # ── Step 2: Convert to Markdown ─────────────────────────────────────────
    logger.info("\nConverting articles to Markdown...")
    articles_dir = Path("articles")
    saved = save_articles(articles, output_dir=articles_dir)
    logger.info("Converted %d articles to Markdown [OK]", len(saved))

    # ── Step 3: Delta tracking ──────────────────────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info("STEP 2 — Calculating Delta and Updating State")
    logger.info("=" * 60)

    # Use a separate state file for Gemini so we don't mess up OpenAI's file IDs
    tracker = DeltaTracker(Path("state/hashes_gemini.json"))

    added = updated = skipped = errors = 0
    current_slugs = set()

    for article_info in saved:
        slug = article_info["slug"]
        filepath = Path(article_info["path"])
        updated_at = article_info["updated_at"]
        current_slugs.add(slug)

        try:
            content = filepath.read_text(encoding="utf-8")
            action = tracker.classify(slug, content)

            if action == "skip":
                skipped += 1
                continue
            elif action == "add":
                tracker.record(slug, content, file_id="local", updated_at=updated_at)
                logger.info("  [ADD]    %s", slug)
                added += 1
            elif action == "update":
                tracker.record(slug, content, file_id="local", updated_at=updated_at)
                logger.info("  [UPDATE] %s", slug)
                updated += 1

        except Exception as exc:
            logger.error("  [ERROR]  Failed to process %s: %s", slug, exc)
            errors += 1

    # Remove any articles that no longer exist
    for tracked_slug in tracker.all_slugs():
        if tracked_slug not in current_slugs:
            logger.info("  [DELETE] %s (no longer exists)", tracked_slug)
            tracker.remove(tracked_slug)

    tracker.save()

    # ── Step 4: Summary ─────────────────────────────────────────────────────
    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

    logger.info("\n" + "=" * 60)
    logger.info("SYNC COMPLETE")
    logger.info("=" * 60)
    logger.info("  [ADD] Added:      %d", added)
    logger.info("  [UPDATE] Updated:    %d", updated)
    logger.info("  [SKIP] Skipped:    %d", skipped)
    logger.info("  [ERROR] Errors:     %d", errors)
    logger.info("  Duration:          %.1f seconds", elapsed)
    logger.info("  Log:               %s", log_file.resolve())
    logger.info("")
    logger.info("  Next step: python test_gemini.py")


if __name__ == "__main__":
    run_sync()
