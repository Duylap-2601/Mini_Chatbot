# OptiBot Support Sync

An automated pipeline that scrapes the OptiSigns Help Center, converts articles to Markdown, and syncs them into an OpenAI Vector Store to power a RAG-based customer support assistant.

---

## Architecture

```
Zendesk API  →  Markdown files  →  OpenAI Vector Store  →  OptiBot Assistant
     ↑                                      ↑
  Daily cron (Railway)          Delta detection (SHA-256 hash)
```

---

## Quick Start

### 1. Prerequisites

- Python 3.11+
- Docker (optional, for containerised runs)
- An OpenAI API key with Assistants API access → [platform.openai.com](https://platform.openai.com)

### 2. Clone & install

```bash
git clone https://github.com/<your-username>/optibot-support-sync
cd optibot-support-sync
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.sample .env
# Edit .env and set OPENAI_API_KEY=sk-...
```

### 4. One-time setup — create Assistant & Vector Store

```bash
python setup_assistant.py
```

Copy the printed `OPENAI_ASSISTANT_ID` and `OPENAI_VECTOR_STORE_ID` into your `.env` file.

### 5. Run the sync pipeline

```bash
python main.py
```

**First run:** scrapes all articles, uploads everything, logs `Added: N`.  
**Subsequent runs:** only uploads changed/new articles, logs `Added: X | Updated: Y | Skipped: Z`.

---

## Running with Docker

### Build & run once

```bash
docker build -t optibot-sync .
docker run --env-file .env \
           -v $(pwd)/state:/app/state \
           -v $(pwd)/logs:/app/logs \
           optibot-sync
```

Or with explicit API key:

```bash
docker run \
  -e OPENAI_API_KEY=sk-... \
  -e OPENAI_VECTOR_STORE_ID=vs-... \
  -v $(pwd)/state:/app/state \
  -v $(pwd)/logs:/app/logs \
  optibot-sync
```

Exits with **code 0** on success, **code 1** if any upload errors occurred.

### Using docker-compose

```bash
docker-compose up --build
```

---

## Project Structure

```
optibot-support-sync/
├── scraper/
│   ├── zendesk_client.py      # Fetch articles from Zendesk Help Center API
│   └── markdown_converter.py  # Convert HTML → clean Markdown + frontmatter
├── vector_store/
│   ├── openai_client.py       # Upload/delete files via OpenAI API (no UI)
│   └── delta_tracker.py       # SHA-256 hash-based change detection
├── state/
│   └── hashes.json            # Persisted state (gitignored)
├── articles/                  # Scraped Markdown files (gitignored)
├── logs/                      # Run logs (gitignored)
├── main.py                    # Orchestrator
├── setup_assistant.py         # One-time Assistant + Vector Store creation
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.sample
```

---

## Chunking Strategy

OpenAI's `file_search` tool handles chunking automatically when files are attached to a Vector Store. The strategy used:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Chunk size | **800 tokens** (OpenAI default) | Preserves a full how-to section; avoids cutting mid-step |
| Overlap | **400 tokens** (OpenAI default) | Ensures context isn't lost at chunk boundaries |
| Split priority | Markdown headings (`##`, `###`) | Natural semantic boundaries in support articles |

Each Markdown file includes YAML frontmatter with `url:` and `updated_at:` — these fields are retrieved verbatim in citations so the Assistant can output `Article URL: https://...` as required.

**Upload log example (first run):**
```
✅ Added:   187
🔄 Updated: 0
⏭  Skipped: 0
❌ Errors:  0
⏱  Duration: 142.3s
```

---

## Delta Detection

On each run, `delta_tracker.py` computes a SHA-256 hash of every article's Markdown content and compares it to the stored hash in `state/hashes.json`:

| Hash comparison | Action |
|----------------|--------|
| Slug not seen before | **ADD** — upload new file |
| Hash changed | **UPDATE** — delete old file, upload new |
| Hash unchanged | **SKIP** — no API call made |

This avoids re-uploading the full corpus on every run and keeps API costs minimal.

---

## Daily Deployment (Railway)

The job runs daily at **02:00 UTC** on [Railway](https://railway.app):

1. Connect GitHub repo → Railway auto-builds the Docker image
2. Set environment variables in Railway dashboard
3. Configure cron: `0 2 * * *`

**Latest run log:** [View on Railway →](https://railway.app) *(link will be live after first deploy)*

---

## Assistant Behaviour

The OptiBot Assistant is configured with this system prompt:

> You are OptiBot, a helpful support assistant for OptiSigns.
> - Tone: helpful, accurate, and concise
> - Only answer based on the documentation provided to you
> - Maximum 5 bullet points; if more detail is needed, link to the relevant article
> - Cite at most 3 sources per answer using: `Article URL: <url>`
> - If you cannot find the answer, direct the user to support.optisigns.com

### Sample interaction

**Q:** How do I add a YouTube video?

**A:**
- Go to **Apps** in your OptiSigns dashboard and search for "YouTube"
- Click **Add** and paste the YouTube video URL
- Set the display duration and click **Save**
- Assign the app to a screen via **Playlists** or **Quick Assign**

Article URL: https://support.optisigns.com/hc/en-us/articles/...

*(Screenshot: see `/docs/screenshot_youtube_answer.png`)*

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | ✅ | Your OpenAI API key |
| `OPENAI_VECTOR_STORE_ID` | ✅ | Created by `setup_assistant.py` |
| `OPENAI_ASSISTANT_ID` | Optional | For reference/logging |
