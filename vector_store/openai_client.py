"""
openai_client.py — Upload Markdown files to OpenAI Vector Store via API.

Uses:
  - openai.files.create()              to upload file content
  - openai.vector_stores.files.*       to attach/remove from vector store
  - openai.vector_stores.file_batches  to batch attach files for speed
"""

import os
import time
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI

logger = logging.getLogger(__name__)


class VectorStoreClient:
    def __init__(self, api_key: str, vector_store_id: str):
        self.client = OpenAI(api_key=api_key)
        self.vs_id = vector_store_id

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def upload_file(self, filepath: Path) -> str:
        """
        Upload a Markdown file to OpenAI Files API.
        Returns the file_id (e.g. 'file-abc123').
        """
        with open(filepath, "rb") as f:
            response = self.client.files.create(
                file=(filepath.name, f, "text/plain"),
                purpose="assistants",
            )
        file_id = response.id
        logger.debug(f"    Uploaded {filepath.name} -> {file_id}")
        return file_id

    def upload_files_parallel(self, filepaths: list[Path], max_workers: int = 10) -> dict[Path, str]:
        """
        Upload multiple files in parallel.
        Returns dict mapping Path -> file_id.
        """
        results = {}
        if not filepaths:
            return results

        logger.info(f"Uploading {len(filepaths)} files in parallel (workers={max_workers})...")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_path = {executor.submit(self.upload_file, path): path for path in filepaths}
            for future in as_completed(future_to_path):
                path = future_to_path[future]
                try:
                    file_id = future.result()
                    results[path] = file_id
                except Exception as e:
                    logger.error(f"Failed to upload {path.name}: {e}")
                    raise e
        return results

    def delete_file(self, file_id: str):
        """Delete a file from OpenAI Files API."""
        try:
            self.client.files.delete(file_id)
            logger.debug(f"    Deleted old file {file_id}")
        except Exception as e:
            logger.warning(f"    Could not delete file {file_id}: {e}")

    # ------------------------------------------------------------------
    # Vector Store attachment
    # ------------------------------------------------------------------

    def attach_files_batch(self, file_ids: list[str]):
        """
        Attach multiple files to the vector store in a single batch operation.
        Waits for completion.
        """
        if not file_ids:
            return

        logger.info(f"Submitting batch of {len(file_ids)} files to Vector Store...")
        batch = self.client.vector_stores.file_batches.create_and_poll(
            vector_store_id=self.vs_id,
            file_ids=file_ids,
        )

        logger.info(f"Batch completed with status: {batch.status}")
        if batch.status == "failed":
            logger.error(f"Batch failed. File counts: {batch.file_counts}")
            raise RuntimeError(f"Vector Store batch processing failed: {batch}")
        elif batch.file_counts.failed > 0:
            logger.warning(f"Some files in batch failed to index: {batch.file_counts}")

    def detach_from_vector_store(self, file_id: str):
        """Remove a file attachment from the vector store."""
        try:
            self.client.vector_stores.files.delete(
                vector_store_id=self.vs_id,
                file_id=file_id,
            )
            logger.debug(f"    Detached {file_id} from vector store")
        except Exception as e:
            logger.warning(f"    Could not detach {file_id}: {e}")

    def detach_and_delete_old_files(self, file_ids: list[str], max_workers: int = 10):
        """Detach and delete old files in parallel."""
        if not file_ids:
            return

        logger.info(f"Detaching and deleting {len(file_ids)} old files in parallel...")
        def cleanup(fid):
            self.detach_from_vector_store(fid)
            self.delete_file(fid)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(cleanup, fid) for fid in file_ids]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.warning(f"Error cleaning up old file: {e}")

    # ------------------------------------------------------------------
    # Vector store info
    # ------------------------------------------------------------------

    def get_vector_store_info(self) -> dict:
        vs = self.client.vector_stores.retrieve(self.vs_id)
        return {
            "id": vs.id,
            "name": vs.name,
            "file_counts": vs.file_counts.model_dump() if vs.file_counts else {},
        }

