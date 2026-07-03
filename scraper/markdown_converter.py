"""
markdown_converter.py — Convert Zendesk article HTML to clean Markdown files.

Keeps: headings, code blocks, relative links, bullet lists, numbered lists.
Removes: nav menus, breadcrumbs, footer, empty sections, script/style tags.
Adds: YAML frontmatter with title, url, updated_at.
"""

import re
import os
import logging
from pathlib import Path
from bs4 import BeautifulSoup
from markdownify import markdownify as md

logger = logging.getLogger(__name__)

# Output directory for .md files
ARTICLES_DIR = Path("articles")


def _clean_html(html: str) -> str:
    """Remove noise elements from raw Zendesk article HTML."""
    soup = BeautifulSoup(html, "lxml")

    # Remove non-content tags
    noise_tags = [
        "script", "style", "nav", "footer", "header",
        "aside", "iframe", "noscript", "form",
    ]
    for tag in noise_tags:
        for el in soup.find_all(tag):
            el.decompose()

    # Remove elements with known noisy CSS classes (Zendesk-specific)
    noise_classes = [
        "breadcrumbs", "article-votes", "article-footer",
        "article-sidebar", "related-articles", "cookie-banner",
        "feedback", "promotion", "nav-secondary",
    ]
    for cls in noise_classes:
        for el in soup.find_all(class_=re.compile(cls, re.I)):
            el.decompose()

    # Return just the body content as cleaned HTML string
    body = soup.find("body")
    return str(body) if body else str(soup)


def _html_to_markdown(html: str) -> str:
    """Convert cleaned HTML to Markdown with sensible options."""
    raw_md = md(
        html,
        heading_style="ATX",   # Use # ## ### style headings
        bullets="-",           # Use - for bullet lists
        newline_style="backslash",
        strip=["script", "style", "nav", "footer", "header"],
    )

    # Remove excessive blank lines (more than 2 consecutive)
    raw_md = re.sub(r"\n{3,}", "\n\n", raw_md)

    # Strip trailing whitespace per line
    lines = [line.rstrip() for line in raw_md.splitlines()]
    return "\n".join(lines).strip()


def _slugify(text: str) -> str:
    """Convert title/slug to safe filename."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")[:100]  # Max 100 chars


def _build_frontmatter(article: dict) -> str:
    """Build YAML frontmatter block for the article."""
    title = article.get("title", "").replace('"', '\\"')
    url = article.get("html_url", "")
    updated_at = article.get("updated_at", "")
    article_id = article.get("id", "")
    return (
        f"---\n"
        f'title: "{title}"\n'
        f"url: {url}\n"
        f"updated_at: {updated_at}\n"
        f"article_id: {article_id}\n"
        f"---\n\n"
    )


def convert_article(article: dict) -> tuple[str, str]:
    """
    Convert a Zendesk article dict to Markdown.

    Returns:
        (filename, markdown_content)
    """
    html_body = article.get("body", "") or ""
    title = article.get("title", "Untitled")
    slug = article.get("slug") or _slugify(title)

    # Ensure slug is filesystem-safe
    slug = _slugify(slug)
    filename = f"{slug}.md"

    # Build content
    cleaned_html = _clean_html(html_body)
    body_md = _html_to_markdown(cleaned_html)
    frontmatter = _build_frontmatter(article)

    # Add article title as H1 if not already present
    if not body_md.startswith("# "):
        body_md = f"# {title}\n\n{body_md}"

    content = frontmatter + body_md
    return filename, content


def save_articles(articles: list[dict], output_dir: Path = ARTICLES_DIR) -> list[dict]:
    """
    Convert and save all articles as Markdown files.

    Returns list of dicts: [{slug, filename, path, updated_at}]
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    saved = []

    for article in articles:
        try:
            filename, content = convert_article(article)
            filepath = output_dir / filename

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

            saved.append({
                "slug": filename.replace(".md", ""),
                "filename": filename,
                "path": str(filepath),
                "updated_at": article.get("updated_at", ""),
                "html_url": article.get("html_url", ""),
            })
            logger.debug(f"  Saved: {filename}")

        except Exception as e:
            logger.error(f"  Failed to convert article {article.get('id')}: {e}")

    logger.info(f"Saved {len(saved)}/{len(articles)} articles to {output_dir}/")
    return saved
