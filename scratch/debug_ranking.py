import os
import re
from pathlib import Path

STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "else", "when",
    "at", "from", "by", "for", "with", "about", "against", "between",
    "into", "through", "during", "before", "after", "above", "below",
    "to", "in", "on", "of", "for", "is", "are", "was", "were", "be",
    "been", "being", "have", "has", "had", "having", "do", "does", "did",
    "doing", "how", "what", "why", "where", "who", "which", "this", "that",
    "these", "those", "i", "you", "he", "she", "it", "we", "they", "my",
    "your", "his", "her", "its", "our", "their", "can", "do", "does", "did",
    "optisigns" # Added
}

def debug_ranking(question: str):
    words = re.findall(r"\b\w+\b", question.lower())
    keywords = [w for w in words if w not in STOP_WORDS and len(w) > 2]
    print("Keywords:", keywords)

    scored_articles = []
    articles_dir = Path("articles")
    md_files = sorted(articles_dir.glob("*.md"))

    for path in md_files:
        content = path.read_text(encoding="utf-8")
        content_lower = content.lower()

        title = ""
        for line in content_lower.splitlines():
            if line.startswith("# ") or line.startswith("title:"):
                title = line
                break

        score = 0
        for kw in keywords:
            # We can also match plurals/singulars slightly by using a simple substring match
            # e.g., if kw is "playlist", it matches "playlists" via `.count("playlist")`
            # Let's count in title
            score += title.count(kw) * 50  # Give title matches even higher weight!
            score += content_lower.count(kw)

        if score > 0:
            scored_articles.append((score, path.name))

    scored_articles.sort(key=lambda x: x[0], reverse=True)
    print("Top 10 matched articles:")
    for score, name in scored_articles[:10]:
        print(f"  Score {score}: {name}")

debug_ranking("How do I create a playlist in OptiSigns?")
