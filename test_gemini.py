"""
test_gemini.py
~~~~~~~~~~~~~~
Interactive test for the OptiBot Gemini assistant.

Usage:
    python test_gemini.py

Prerequisite:
    1. Set GOOGLE_API_KEY in your .env file
    2. Run the sync job first:  python main_gemini.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Validate environment
# ---------------------------------------------------------------------------
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
ARTICLES_DIR   = Path(os.getenv("ARTICLES_DIR", "articles"))

if not GOOGLE_API_KEY:
    print("[ERROR] GOOGLE_API_KEY is not set.")
    print("  1. Get a free API key at: https://aistudio.google.com/app/apikey")
    print("  2. Add it to your .env file: GOOGLE_API_KEY=your_key_here")
    sys.exit(1)

if not ARTICLES_DIR.exists() or not any(ARTICLES_DIR.glob("*.md")):
    print(f"[ERROR] No articles found in '{ARTICLES_DIR}'.")
    print("  Run the sync job first:  python main_gemini.py")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
from vector_store.gemini_client import GeminiRAGClient

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
BANNER = """
╔══════════════════════════════════════════════════════════╗
║           OptiBot — Powered by Google Gemini             ║
║          (Context: OptiSigns Help Center Docs)           ║
╚══════════════════════════════════════════════════════════╝
  Type your question and press Enter.
  Commands: 'quit' | 'exit' | 'stats'
"""

# ---------------------------------------------------------------------------
# Pre-built test questions
# ---------------------------------------------------------------------------
DEMO_QUESTIONS = [
    "How do I schedule content to display at a specific time on OptiSigns?",
    "How do I add a new screen to my account?",
    "What file formats does OptiSigns support for media upload?",
    "How do I create a playlist in OptiSigns?",
    "How do I set up a Canva integration with OptiSigns?",
]


def run_demo(client: GeminiRAGClient) -> None:
    """Run the 5 pre-built questions automatically (non-interactive demo)."""
    print("\n[DEMO MODE] Running 5 sample questions...\n")
    for i, question in enumerate(DEMO_QUESTIONS, 1):
        print(f"Q{i}: {question}")
        print("-" * 60)
        answer = client.ask(question)
        print(answer)
        print()


def run_interactive(client: GeminiRAGClient) -> None:
    """Interactive REPL loop."""
    print(BANNER)

    print(f"  Articles loaded : {client.article_count()}")
    print()

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit"):
            print("Goodbye!")
            break

        if user_input.lower() == "stats":
            print(f"  Articles: {client.article_count()}")
            continue

        print("\nOptiBot:", end=" ", flush=True)
        try:
            answer = client.ask(user_input)
            print(answer)
        except Exception as exc:
            print(f"[ERROR] {exc}")
        print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    client = GeminiRAGClient(api_key=GOOGLE_API_KEY, articles_dir=ARTICLES_DIR)

    if "--demo" in sys.argv:
        run_demo(client)
    else:
        run_interactive(client)
