"""
delta_tracker.py — SHA-256 hash-based change detection for articles.

Stores state in state/hashes.json:
{
  "slug": {
    "hash": "sha256-of-content",
    "file_id": "file-abc123",   ← OpenAI file ID
    "vs_file_id": "..."         ← vector store file attachment ID
    "updated_at": "2024-01-15T..."
  }
}
"""

import json
import hashlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_STATE_FILE = Path("state/hashes.json")


class DeltaTracker:
    def __init__(self, state_file: Path = DEFAULT_STATE_FILE):
        self.state_file = Path(state_file)
        self.state: dict[str, dict] = self._load()

    def _load(self) -> dict:
        if self.state_file.exists():
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def save(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)
        logger.info(f"State saved to {self.state_file} ({len(self.state)} entries)")

    @staticmethod
    def hash_content(content: str) -> str:
        """SHA-256 hash of article content (UTF-8 encoded)."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def classify(self, slug: str, content: str) -> str:
        """
        Compare current content hash against stored state.

        Returns:
            "add"     — new article, not seen before
            "update"  — content changed since last run
            "skip"    — content unchanged
        """
        new_hash = self.hash_content(content)
        existing = self.state.get(slug)

        if existing is None:
            return "add"
        if existing["hash"] != new_hash:
            return "update"
        return "skip"

    def get_file_id(self, slug: str) -> str | None:
        """Return stored OpenAI file_id for a slug (for deletion on update)."""
        entry = self.state.get(slug)
        return entry.get("file_id") if entry else None

    def record(self, slug: str, content: str, file_id: str, updated_at: str = ""):
        """Update state entry after a successful upload."""
        self.state[slug] = {
            "hash": self.hash_content(content),
            "file_id": file_id,
            "updated_at": updated_at,
        }

    def remove(self, slug: str):
        """Remove a slug from state (article deleted from source)."""
        self.state.pop(slug, None)

    def all_slugs(self) -> set[str]:
        """Return all slugs currently tracked."""
        return set(self.state.keys())
