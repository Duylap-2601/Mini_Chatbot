"""
main.py — Orchestrator: Scrape OptiSigns Help Center → Upload delta to OpenAI Vector Store.

Usage:
    python main.py

Environment variables (see .env.sample):
    OPENAI_API_KEY
    OPENAI_VECTOR_STORE_ID
    OPENAI_ASSISTANT_ID  (optional, for logging)
"""

import os
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Load .env before importing project modules
load_dotenv()

from scraper.zendesk_client import fetch_all_articles
from scraper.markdown_converter import save_articles
from vector_store.delta_tracker import DeltaTracker
from vector_store.openai_client import VectorStoreClient

# ---------------------------------------------------------------------------
# Logging setup — writes to both stdout and logs/run_<timestamp>.log
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------
def get_config() -> dict:
    required = ["OPENAI_API_KEY", "OPENAI_VECTOR_STORE_ID"]
    config = {}
    missing = []

    for key in required:
        val = os.getenv(key)
        if not val or val.startswith("sk-...") or val.startswith("vs_..."):
            missing.append(key)
        config[key] = val

    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        logger.error("Copy .env.sample → .env and fill in your credentials.")
        sys.exit(1)

    return config


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def run_pipeline(config: dict) -> dict:
    stats = {"added": 0, "updated": 0, "skipped": 0, "errors": 0}

    # ── Step 1: Scrape ──────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 1 — Scraping OptiSigns Help Center articles")
    logger.info("=" * 60)

    articles = fetch_all_articles()

    if len(articles) < 30:
        logger.warning(f"Only fetched {len(articles)} articles — expected >=30!")
    else:
        logger.info(f"Fetched {len(articles)} articles [OK]")

    # ── Step 2: Convert to Markdown ─────────────────────────────────────────
    logger.info("\nConverting articles to Markdown...")
    saved = save_articles(articles, output_dir=Path("articles"))
    logger.info(f"Converted {len(saved)} articles to Markdown [OK]")

    # ── Step 3: Delta detection + upload ────────────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info("STEP 2 — Uploading delta to OpenAI Vector Store")
    logger.info("=" * 60)

    tracker = DeltaTracker(Path("state/hashes.json"))
    vs_client = VectorStoreClient(
        api_key=config["OPENAI_API_KEY"],
        vector_store_id=config["OPENAI_VECTOR_STORE_ID"],
    )

    # Print vector store status
    try:
        info = vs_client.get_vector_store_info()
        logger.info(f"Vector Store: {info['name']} ({info['id']})")
        logger.info(f"  Current file counts: {info['file_counts']}")
    except Exception as e:
        logger.warning(f"Could not fetch vector store info: {e}")

    # Process each saved article to classify action
    to_add = []      # list of (slug, filepath, content, updated_at)
    to_update = []   # list of (slug, filepath, content, updated_at, old_file_id)
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
                logger.debug(f"  [SKIP]    {slug}")
                continue
            elif action == "add":
                to_add.append((slug, filepath, content, updated_at))
            elif action == "update":
                old_file_id = tracker.get_file_id(slug)
                to_update.append((slug, filepath, content, updated_at, old_file_id))
        except Exception as e:
            logger.error(f"  [ERROR]   Failed to classify {slug}: {e}")
            stats["errors"] += 1

    # Print summary of pending actions
    logger.info(f"Classified: {len(to_add)} additions, {len(to_update)} updates, {stats['skipped']} skips.")

    # 1. Clean up old files for updates
    old_file_ids = [item[4] for item in to_update if item[4]]
    if old_file_ids:
        try:
            vs_client.detach_and_delete_old_files(old_file_ids)
        except Exception as e:
            logger.warning(f"Error during cleanup of old files: {e}")

    # 2. Upload new/updated files in parallel
    paths_to_upload = [item[1] for item in to_add] + [item[1] for item in to_update]
    uploaded_files_map = {}
    if paths_to_upload:
        try:
            uploaded_files_map = vs_client.upload_files_parallel(paths_to_upload)
        except Exception as e:
            logger.error(f"Error uploading files: {e}")
            stats["errors"] += len(paths_to_upload)
            tracker.save()
            return stats

    # 3. Attach all uploaded file IDs to vector store in a batch
    uploaded_file_ids = list(uploaded_files_map.values())
    if uploaded_file_ids:
        try:
            vs_client.attach_files_batch(uploaded_file_ids)
            
            # 4. If batch attachment succeeded, record everything in state
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
            logger.error(f"Error indexing files in Vector Store: {e}")
            stats["errors"] += len(uploaded_file_ids)

    # ── Step 4: Save state ──────────────────────────────────────────────────
    tracker.save()

    return stats


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    run_start = datetime.now(timezone.utc)
    logger.info(f"OptiBot Sync Job started at {run_start.isoformat()}")
    logger.info(f"Log file: {log_file.resolve()}")

    config = get_config()
    stats = run_pipeline(config)

    run_end = datetime.now(timezone.utc)
    duration = (run_end - run_start).total_seconds()

    logger.info("\n" + "=" * 60)
    logger.info("SYNC COMPLETE")
    logger.info("=" * 60)
    logger.info(f"  [ADD] Added:   {stats['added']}")
    logger.info(f"  [UPDATE] Updated: {stats['updated']}")
    logger.info(f"  [SKIP] Skipped: {stats['skipped']}")
    logger.info(f"  [ERROR] Errors:  {stats['errors']}")
    logger.info(f"  Duration: {duration:.1f}s")
    logger.info(f"  Log: {log_file.resolve()}")

    if stats["errors"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
