"""
gemini_client.py
~~~~~~~~~~~~~~~~
RAG client using the official new Google GenAI SDK.

Strategy: Hybrid Local Keyword Ranking + Context Stuffing
  - Since the Gemini free tier has a 250,000 input token/minute limit,
    sending all 404 articles (~500k tokens) at once causes rate limiting.
  - Instead, we run a fast local keyword search (TF-IDF style scoring) in Python.
  - We select the top 15 most relevant articles (~30k tokens).
  - This stays well below the rate limit, runs faster, and maintains high accuracy.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# Common stop words to filter out before keyword matching
STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "else", "when",
    "at", "from", "by", "for", "with", "about", "against", "between",
    "into", "through", "during", "before", "after", "above", "below",
    "to", "in", "on", "of", "for", "is", "are", "was", "were", "be",
    "been", "being", "have", "has", "had", "having", "do", "does", "did",
    "doing", "how", "what", "why", "where", "who", "which", "this", "that",
    "these", "those", "i", "you", "he", "she", "it", "we", "they", "my",
    "your", "his", "her", "its", "our", "their", "can", "do", "does", "did",
    "optisigns"
}

SYSTEM_INSTRUCTION = """You are OptiBot, a helpful support assistant for OptiSigns — a leading digital signage platform.

Rules you must follow:
- Tone: professional, friendly, and concise.
- Answer ONLY based on the documentation provided in the context. Do NOT use outside knowledge.
- Keep answers focused: use bullet points when listing steps or options.
- After your answer, cite up to 3 relevant article URLs found in the documentation using this format:
    Sources:
    - <title>: <url>
- If the answer is not found in the documentation, respond exactly:
    "I don't have information on that topic. Please visit https://support.optisigns.com or contact OptiSigns support directly."
"""


class GeminiRAGClient:
    """
    Wraps Google Gemini API with local keyword-based ranking RAG.

    Usage:
        client = GeminiRAGClient(api_key="...", articles_dir=Path("articles"))
        answer = client.ask("How do I schedule content on OptiSigns?")
    """

    def __init__(
        self,
        api_key: str,
        articles_dir: Path = Path("articles"),
        model_name: str = "gemini-2.5-flash",
    ) -> None:
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name
        self.articles_dir = Path(articles_dir)

    def article_count(self) -> int:
        """Return how many article files are available locally."""
        return len(list(self.articles_dir.glob("*.md")))

    def _get_relevant_context(self, question: str, top_n: int = 15) -> str:
        """
        Extract keywords from the question and rank all articles by keyword frequency.
        Returns a single markdown string with the top_n most relevant articles.
        """
        # Clean and extract keywords
        words = re.findall(r"\b\w+\b", question.lower())
        keywords = [w for w in words if w not in STOP_WORDS and len(w) > 2]

        if not keywords:
            # Fallback to all words if they are all stop words
            keywords = [w for w in words if len(w) > 1]

        scored_articles: list[tuple[int, str]] = []
        md_files = sorted(self.articles_dir.glob("*.md"))

        for path in md_files:
            try:
                content = path.read_text(encoding="utf-8")
                content_lower = content.lower()

                # Find title block for high-priority matching
                title = ""
                for line in content_lower.splitlines():
                    if line.startswith("# ") or line.startswith("title:"):
                        title = line
                        break

                score = 0
                for kw in keywords:
                    # Title matches are weighted heavily (50x)
                    score += title.count(kw) * 50
                    # Body matches are weighted normally (1x)
                    score += content_lower.count(kw)

                if score > 0:
                    scored_articles.append((score, content))
            except Exception as exc:
                logger.warning("Could not read %s: %s", path.name, exc)

        # Sort by score descending
        scored_articles.sort(key=lambda x: x[0], reverse=True)

        if not scored_articles:
            logger.info("No matching articles found. Using fallback first 5 articles.")
            selected_docs = []
            for path in md_files[:5]:
                try:
                    selected_docs.append(path.read_text(encoding="utf-8"))
                except Exception:
                    pass
        else:
            selected_docs = [content for score, content in scored_articles[:top_n]]

        logger.info(
            "Query keywords: %s | Rated %d matches | Selected top %d articles for context",
            keywords, len(scored_articles), len(selected_docs)
        )
        return "\n\n---\n\n".join(selected_docs)

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def ask(self, question: str) -> str:
        """
        Ask a question. The most relevant articles are retrieved locally
        and passed as context.
        """
        context = self._get_relevant_context(question)

        prompt = (
            "=== OptiSigns Support Documentation ===\n\n"
            f"{context}\n\n"
            "=== End of Documentation ===\n\n"
            f"User Question: {question}"
        )

        logger.debug("Sending prompt to Gemini...")

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.2,        # low temp for factual answers
                max_output_tokens=1024,
            )
        )

        return response.text
