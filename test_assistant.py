"""
test_assistant.py — Smoke test for Part 2: send a test question to OptiBot.

Prerequisites:
  - .env must have OPENAI_API_KEY and OPENAI_ASSISTANT_ID set
  - Vector Store must already have files uploaded (run main.py first)

Run: python test_assistant.py
"""

import os
import time
import sys
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

TEST_QUESTION = "How do I add a YouTube video?"


def main():
    api_key = os.getenv("OPENAI_API_KEY")
    assistant_id = os.getenv("OPENAI_ASSISTANT_ID")

    if not api_key or not assistant_id:
        print("ERROR: Set OPENAI_API_KEY and OPENAI_ASSISTANT_ID in .env")
        sys.exit(1)

    client = OpenAI(api_key=api_key)

    print(f"Testing OptiBot with question: '{TEST_QUESTION}'")
    print("-" * 60)

    # Create a thread
    thread = client.beta.threads.create()

    # Add the user message
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=TEST_QUESTION,
    )

    # Run the assistant
    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant_id,
    )

    # Poll until done
    print("Waiting for response", end="", flush=True)
    while run.status in ("queued", "in_progress"):
        time.sleep(1)
        run = client.beta.threads.runs.retrieve(
            thread_id=thread.id,
            run_id=run.id,
        )
        print(".", end="", flush=True)

    print(f"\nStatus: {run.status}\n")

    if run.status != "completed":
        print(f"Run failed: {run.last_error}")
        sys.exit(1)

    # Get the assistant's reply
    messages = client.beta.threads.messages.list(thread_id=thread.id)
    reply = messages.data[0]  # Most recent message

    print("=" * 60)
    print("OptiBot Answer:")
    print("=" * 60)
    for block in reply.content:
        if hasattr(block, "text"):
            print(block.text.value)

    print("\n✅ Test complete! Take a screenshot of this output for your submission.")


if __name__ == "__main__":
    main()
