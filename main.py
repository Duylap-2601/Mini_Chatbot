"""
main.py — Orchestrator: Scrape OptiSigns Help Center → Sync to AI Assistant.

Supports:
  1. Google Gemini (Free tier) — Runs when GOOGLE_API_KEY or an AIza... API_KEY is set.
  2. OpenAI Assistants API — Runs when OPENAI_API_KEY or a sk-... API_KEY is set.

Automatic detection of key format:
  - starts with "sk-": OpenAI
  - starts with "AIza": Google Gemini
"""

from __future__ import annotations

import os
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Load .env before importing project modules
load_dotenv()

# Configure environment fallback for "API_KEY" as specified in recruiting guidelines
generic_api_key = os.getenv("API_KEY")
if generic_api_key:
    if generic_api_key.startswith("sk-"):
        os.environ["OPENAI_API_KEY"] = generic_api_key
    elif generic_api_key.startswith("AIza"):
        os.environ["GOOGLE_API_KEY"] = generic_api_key
    else:
        # If unknown, set both just in case
        os.environ["OPENAI_API_KEY"] = generic_api_key
        os.environ["GOOGLE_API_KEY"] = generic_api_key

# Setup logging — writes to both stdout and logs/run_<timestamp>.log
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

# Project imports
from scraper.zendesk_client import fetch_all_articles
from scraper.markdown_converter import save_articles
from vector_store.delta_tracker import DeltaTracker

# ---------------------------------------------------------------------------
# Pipeline 1: Google Gemini (Context stuffing + local keyword ranking RAG)
# ---------------------------------------------------------------------------
def run_gemini_pipeline() -> dict:
    logger.info("Executing pipeline: GOOGLE GEMINI (Local Delta Sync)")
    stats = {"added": 0, "updated": 0, "skipped": 0, "errors": 0}

    # 1. Scrape
    logger.info("=" * 60)
    logger.info("STEP 1 — Scraping OptiSigns Help Center articles")
    logger.info("=" * 60)
    articles = fetch_all_articles()
    logger.info("Fetched %d articles", len(articles))

    # 2. Convert to Markdown
    logger.info("\nConverting articles to Markdown...")
    saved = save_articles(articles, output_dir=Path("articles"))
    logger.info("Converted %d articles to Markdown [OK]", len(saved))

    # 3. Delta tracking (local hashes)
    logger.info("\n" + "=" * 60)
    logger.info("STEP 2 — Calculating Delta and Updating State")
    logger.info("=" * 60)

    tracker = DeltaTracker(Path("state/hashes_gemini.json"))
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
                stats["skipped"] += 1
                continue
            elif action == "add":
                tracker.record(slug, content, file_id="local", updated_at=updated_at)
                logger.info("  [ADD]    %s", slug)
                stats["added"] += 1
            elif action == "update":
                tracker.record(slug, content, file_id="local", updated_at=updated_at)
                logger.info("  [UPDATE] %s", slug)
                stats["updated"] += 1
        except Exception as exc:
            logger.error("  [ERROR]  Failed to process %s: %s", slug, exc)
            stats["errors"] += 1

    # Remove deleted articles
    for tracked_slug in tracker.all_slugs():
        if tracked_slug not in current_slugs:
            logger.info("  [DELETE] %s (no longer exists)", tracked_slug)
            tracker.remove(tracked_slug)
            
    tracker.save()
    return stats

# ---------------------------------------------------------------------------
# Pipeline 2: OpenAI (Cloud Assistants API + Vector Store)
# ---------------------------------------------------------------------------
def run_openai_pipeline() -> dict:
    logger.info("Executing pipeline: OPENAI ASSISTANTS (Cloud Vector Store Sync)")
    from vector_store.openai_client import VectorStoreClient
    
    openai_key = os.getenv("OPENAI_API_KEY")
    vs_id = os.getenv("OPENAI_VECTOR_STORE_ID")

    if not openai_key or not vs_id:
        logger.error("Missing required env: OPENAI_API_KEY and OPENAI_VECTOR_STORE_ID must be set.")
        sys.exit(1)

    stats = {"added": 0, "updated": 0, "skipped": 0, "errors": 0}

    # 1. Scrape
    logger.info("=" * 60)
    logger.info("STEP 1 — Scraping OptiSigns Help Center articles")
    logger.info("=" * 60)
    articles = fetch_all_articles()
    logger.info("Fetched %d articles", len(articles))

    # 2. Convert to Markdown
    logger.info("\nConverting articles to Markdown...")
    saved = save_articles(articles, output_dir=Path("articles"))
    logger.info("Converted %d articles to Markdown [OK]", len(saved))

    # 3. Delta detection + upload
    logger.info("\n" + "=" * 60)
    logger.info("STEP 2 — Uploading delta to OpenAI Vector Store")
    logger.info("=" * 60)

    tracker = DeltaTracker(Path("state/hashes.json"))
    vs_client = VectorStoreClient(api_key=openai_key, vector_store_id=vs_id)

    try:
        info = vs_client.get_vector_store_info()
        logger.info("Vector Store: %s (%s)", info["name"], info["id"])
        logger.info("  Current file counts: %s", info["file_counts"])
    except Exception as e:
        logger.warning("Could not fetch vector store info: %s", e)

    to_add = []
    to_update = []
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
                stats["skipped"] += 1
                continue
            elif action == "add":
                to_add.append((slug, filepath, content, updated_at))
            elif action == "update":
                old_file_id = tracker.get_file_id(slug)
                to_update.append((slug, filepath, content, updated_at, old_file_id))
        except Exception as e:
            logger.error("  [ERROR]   Failed to classify %s: %s", slug, e)
            stats["errors"] += 1

    logger.info("Classified: %d additions, %d updates, %d skips.", len(to_add), len(to_update), stats["skipped"])

    # Detach and delete old files
    old_file_ids = [item[4] for item in to_update if item[4]]
    if old_file_ids:
        try:
            vs_client.detach_and_delete_old_files(old_file_ids)
        except Exception as e:
            logger.warning("Error cleaning up old files: %s", e)

    # Parallel upload
    paths_to_upload = [item[1] for item in to_add] + [item[1] for item in to_update]
    uploaded_files_map = {}
    if paths_to_upload:
        try:
            uploaded_files_map = vs_client.upload_files_parallel(paths_to_upload)
        except Exception as e:
            logger.error("Error uploading files: %s", e)
            stats["errors"] += len(paths_to_upload)
            tracker.save()
            return stats

    # Attach in batch
    uploaded_file_ids = list(uploaded_files_map.values())
    if uploaded_file_ids:
        try:
            vs_client.attach_files_batch(uploaded_file_ids)
            
            # Record additions
            for slug, filepath, content, updated_at in to_add:
                file_id = uploaded_files_map.get(filepath)
                if file_id:
                    tracker.record(slug, content, file_id, updated_at)
                    stats["added"] += 1
                else:
                    stats["errors"] += 1
                    
            # Record updates
            for slug, filepath, content, updated_at, old_file_id in to_update:
                file_id = uploaded_files_map.get(filepath)
                if file_id:
                    tracker.record(slug, content, file_id, updated_at)
                    stats["updated"] += 1
                else:
                    stats["errors"] += 1
        except Exception as e:
            logger.error("Error indexing files in Vector Store: %s", e)
            stats["errors"] += len(uploaded_file_ids)

    # Remove deleted articles from state and OpenAI Vector Store
    for tracked_slug in tracker.all_slugs():
        if tracked_slug not in current_slugs:
            old_file_id = tracker.get_file_id(tracked_slug)
            if old_file_id:
                logger.info("  [DELETE] %s from OpenAI Vector Store", tracked_slug)
                try:
                    vs_client.detach_from_vector_store(old_file_id)
                    vs_client.delete_file(old_file_id)
                except Exception as e:
                    logger.warning("Error detaching deleted file: %s", e)
            tracker.remove(tracked_slug)

    tracker.save()
    return stats

# ---------------------------------------------------------------------------
# Main Orchestrator Entry Point
# ---------------------------------------------------------------------------
def main():
    run_start = datetime.now(timezone.utc)
    logger.info("OptiBot Sync Job started at %s", run_start.isoformat())
    logger.info("Log file: %s", log_file.resolve())

    # Detect which API key is present
    google_key = os.getenv("GOOGLE_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if google_key:
        stats = run_gemini_pipeline()
    elif openai_key:
        stats = run_openai_pipeline()
    else:
        logger.error("ERROR: Neither GOOGLE_API_KEY nor OPENAI_API_KEY (or API_KEY) is set.")
        logger.error("Please configure environment variables.")
        sys.exit(1)

    run_end = datetime.now(timezone.utc)
    duration = (run_end - run_start).total_seconds()

    logger.info("\n" + "=" * 60)
    logger.info("SYNC COMPLETE")
    logger.info("=" * 60)
    logger.info("  [ADD] Added:      %d", stats["added"])
    logger.info("  [UPDATE] Updated:    %d", stats["updated"])
    logger.info("  [SKIP] Skipped:    %d", stats["skipped"])
    logger.info("  [ERROR] Errors:     %d", stats["errors"])
    logger.info("  Duration:          %.1f seconds", duration)
    logger.info("  Log:               %s", log_file.resolve())

    if stats["errors"] > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
