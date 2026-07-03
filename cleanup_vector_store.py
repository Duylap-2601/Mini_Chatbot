"""
cleanup_vector_store.py — Delete all files from OpenAI Files API and Vector Store
to start with a clean, deduplicated state.
"""

import os
import sys
from dotenv import load_dotenv
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed

load_dotenv()


def main():
    api_key = os.getenv("OPENAI_API_KEY")
    vs_id = os.getenv("OPENAI_VECTOR_STORE_ID")

    if not api_key or not vs_id:
        print("ERROR: Set OPENAI_API_KEY and OPENAI_VECTOR_STORE_ID in .env")
        sys.exit(1)

    client = OpenAI(api_key=api_key)

    # 1. List all files attached to the Vector Store
    print(f"Retrieving files from Vector Store {vs_id}...")
    vs_files = []
    after = None
    while True:
        resp = client.vector_stores.files.list(vector_store_id=vs_id, after=after, limit=100)
        vs_files.extend(resp.data)
        if not resp.data or not hasattr(resp, "has_more") or not resp.has_more:
            break
        after = resp.data[-1].id

    print(f"Found {len(vs_files)} files in Vector Store.")

    # 2. List all files in OpenAI Files API
    print("Retrieving files from OpenAI Files API...")
    all_files = client.files.list(purpose="assistants")
    files_to_delete = [f.id for f in all_files.data]
    print(f"Found {len(files_to_delete)} files in OpenAI Files API.")

    if not files_to_delete:
        print("Nothing to delete.")
        sys.exit(0)

    # Confirm
    print(f"This will delete {len(files_to_delete)} files from OpenAI and detach them from the Vector Store.")
    
    # Detach and delete in parallel
    def clean_file(file_id):
        # Detach from vector store
        try:
            client.vector_stores.files.delete(vector_store_id=vs_id, file_id=file_id)
        except Exception:
            pass
        # Delete from Files API
        try:
            client.files.delete(file_id)
            return file_id, True
        except Exception as e:
            return file_id, False

    print("Deleting files in parallel...")
    success_count = 0
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(clean_file, fid) for fid in files_to_delete]
        for future in as_completed(futures):
            fid, success = future.result()
            if success:
                success_count += 1

    print(f"Successfully cleaned up {success_count}/{len(files_to_delete)} files.")

    # Remove hashes.json if it exists
    state_file = "state/hashes.json"
    if os.path.exists(state_file):
        os.remove(state_file)
        print(f"Removed local state file {state_file}")


if __name__ == "__main__":
    main()
