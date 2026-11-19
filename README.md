# BU AI – Intelligent Student Success Platform (independent prototype)

An AI assistant that answers questions about the university from its **public** web pages, with a link to the
official source behind every answer. It runs on its own, with no dependency on Claude's environment.

> Independent student prototype. Not affiliated with or endorsed by Belhaven University. Uses public
> information only, with no student records and no logins to university systems.

## What's included

**Student tools**
| Feature | What it does |
|---|---|
| **Ask** (AI assistant) | Streaming answers with numbered citations to official pages; "I am a…" role selector (8 roles); 12 service tiles; voice input (Chrome, Edge, Safari); replies in the student's language |
| **Program Finder** (`/programs`) | All 88 degrees, certificates and international hybrid programs, filtered by level, format and area, with concentrations |
| **Scholarship & Aid Finder** (`/scholarships`) | Matches 31 scholarships, grants and discounts to the student's type, GPA, ACT and situation (arts, church, military, Mississippi resident…) |
| **Contact Navigator** (`/directory`) | "Who do I contact?" across 33 offices: phone, email, location |
| **Getting started** (`/onboarding`) | Step-by-step first-term checklists for first-year, transfer, international, online and graduate students, with progress saved in the browser |

Every tool has an "Ask about it" button that opens the assistant with the question already filled in.

**Administrator tools** (`/admin`)
- Question analytics: by role and topic, most asked, unanswered (content gaps), helpful rate
- Safety counters: status-risk questions sent to the DSO, personal info removed, AI answers with unverified figures
- **Knowledge monitor**: conflicting facts across pages (TOEFL score, credit hours, office phone numbers), outdated pages, broken links, changed pages

**Trust and safety**
| Control | How |
|---|---|
| Answers only from official sources | Prompt rules plus citations; with no matching source the AI isn't called and it says it couldn't find the answer |
| **Answer verification** | `guard.py` checks each AI answer sentence by sentence: every amount, date, count and credit-hour figure (including single digits like "6 credit hours") must appear in the source *cited in that sentence*, attached to the same subject (a $620 fee given for a 40-meal plan when the page lists $620 for 80 meals is caught). It also flags statements with no citation and promises the sources don't make ("guaranteed admission", "you will be approved"), and removes citations that point nowhere. Optional `VERIFY_WITH_AI=true` adds a second AI review of every answer |
| **Personal information removed** | `redact.py` strips names (any capitalization, after introductions, in sign-offs), emails, U.S. and international phone numbers, street addresses, SEVIS IDs, passport, SSN, A-numbers, USCIS receipt numbers, dates of birth and student ID numbers *before* anything is logged or sent to the AI provider. Only contacts **published in the knowledge base** (office emails, office phones, campus addresses) are kept; the allowlist rebuilds itself whenever content changes |
| Immigration and crisis safety | DSO referral banner for status problems; 988 crisis line for self-harm language |
| Off-topic guard | Unrelated questions (sports, weather, code) get "couldn't find it" instead of a guess |
| Admin security | Admin stays disabled until `ADMIN_TOKEN` passes a strength check (20+ characters, 3 character types, no common words like "admin" or "belhaven"); constant-time comparison; 20 attempts per minute |
| Cost and abuse protection | Per-visitor rate limit (`CHAT_RATE_PER_MINUTE`) and concurrency limit (`MAX_CONCURRENT_PER_IP`); a daily AI cap (`DAILY_AI_LIMIT`) counted in the database and reserved atomically, so restarts, simultaneous requests and closed browser tabs can't exceed it. After the cap, answers fall back to official text |
| Crawler safety | Redirects are followed one hop at a time and blocked if they leave the allowed university hosts |
| Dependencies | Exact versions pinned; `pip-audit` and `npm audit` reported 0 known vulnerabilities at release and run in CI on every push (Next.js upgraded to 16.4.5, pypdf to 6.21.4) |

**Content and architecture**
| Feature | Where |
|---|---|
| 129 searchable passages from 67 official pages, plus structured program, office, scholarship and onboarding data | `backend/data/` |
| Hybrid retrieval: BM25 + vector search, Reciprocal Rank Fusion, role boost | `retrieval.py` |
| Swappable AI provider: Azure OpenAI, OpenAI, Claude, or none | `llm.py` |
| Website crawler that also reads **PDFs** (academic calendars, exam schedules, fee sheets); **automatic refresh** inside the API (`CRAWL_EVERY_HOURS`), and the API picks up content changed by a separate crawler run within `INDEX_WATCH_SECONDS` | `crawl.py`, `main.py` |
| CI: tests, frontend build and Docker images on every push | `.github/workflows/ci.yml` |
| Tests: 99 automated tests, including a regression test for every issue found in review; plus the 100-question validation set in `eval/` | `backend/tests/test_app.py` |

## Run it locally (about 5 minutes)

You need **Python 3.11+** and **Node.js 20+**.

```bash
# 1. Settings
cp .env.example .env            # then edit: set ADMIN_TOKEN and an AI key if you have one
python -c "import secrets; print(secrets.token_urlsafe(24))"   # generates a strong ADMIN_TOKEN

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 3. Frontend (new terminal)
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000** for the assistant and **http://localhost:3000/admin** for insights (use your
`ADMIN_TOKEN`).

Without an AI key it already works: it answers with the matching official text and its citation. To turn
on AI answers, set `LLM_PROVIDER` and that provider's key in `.env`, then restart the backend.

### With Docker (Postgres included)

```bash
cp .env.example .env
docker compose up --build                 # web on :3000, API on :8000, Postgres
docker compose run --rm crawler           # refresh content from the website
```

## "Ask BU AI" website button

A floating button that opens BU AI in a side panel on any web page. On phones it shrinks to a round BU icon and
opens as a bottom sheet. It never opens by itself; Esc or × closes it. Try it at
**http://localhost:3000/website-demo** (a neutral sample page). To add it to a site, one line:

```html
<script src="https://YOUR-BU-AI-HOST/embed.js" defer></script>
```

Optional attributes: `data-label="Ask BU AI"`, `data-position="left"`. Adding it to Belhaven pages is a proposal
that needs the university's approval.

## Refresh content from the website

```bash
cd backend
python -m app.crawl --max 400                       # full refresh from the configured seed pages
python -m app.crawl --url https://www.belhaven.edu/university-life/campus/housing/index.html
```

Or let the API refresh itself: set `CRAWL_EVERY_HOURS=24` in `.env`. This is **off by default on purpose**:
automatically crawling the university's site should be a deliberate choice made after checking with them.

The crawler stays on `www.belhaven.edu` and `igsupport.belhaven.edu`, follows robots.txt, waits 1 second
between requests, and never touches BlazeNet, Canvas, portals or application forms. Crawled text replaces
the seed summary for the same page. To keep answers current, schedule it nightly (cron, Windows Task
Scheduler, or an Azure Container Apps job).

**Before your first full crawl**, check the website's terms of use. Running it from your own computer means
requests come from your IP address.

## Switching AI providers

| Provider | `.env` settings |
|---|---|
| Azure OpenAI | `LLM_PROVIDER=azure`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT`, optional `AZURE_OPENAI_EMBED_DEPLOYMENT` for vector search |
| OpenAI | `LLM_PROVIDER=openai`, `OPENAI_API_KEY` (vector search turns on automatically) |
| Claude | `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY`; add `OPENAI_API_KEY` too if you want vector search |
| None | `LLM_PROVIDER=none` (keyword search plus official-text answers) |

After adding an embeddings key, run `python -m app.ingest --embed` once to compute vectors.

## Architecture

```
Next.js (React) ── /api/chat (SSE stream) ──► FastAPI
                                               ├─ HybridIndex: BM25 + vectors (numpy) → RRF → role boost
                                               ├─ Provider: Azure OpenAI | OpenAI | Claude | extractive
                                               ├─ Guardrails: sources-only, DSO referral, crisis line
                                               └─ SQLAlchemy → SQLite or PostgreSQL
                                                    chunks · pages · queries (anonymous) · issues
Crawler (python -m app.crawl) → extract → chunk → embed → reindex → knowledge monitor
```

### Path to an Azure production deployment (Phase 2/3, after university approval)
- Frontend and API → **Azure Container Apps**; crawler → Container Apps **scheduled job**
- PostgreSQL → **Azure Database for PostgreSQL**; for a large corpus, move vectors to **pgvector** or **Azure AI Search**
  (replace `HybridIndex._vector`)
- `LLM_PROVIDER=azure` keeps student questions inside the university's Azure tenant
- Sign-in with **Microsoft Entra ID**; personalized data only after a FERPA review and the university's IT security approval
- CI/CD with GitHub Actions (`pytest` + `next build`)

## Demo script (12 minutes)
1. **Home**: pick "International", then click **Immigration & CPT/OPT**. The answer cites its sources; point out the "FAQ updated ~2 years ago" labels.
2. Ask *"My SEVIS was terminated, what should I do?"* The DSO safety banner appears.
3. Ask *"My name is Ravi, SEVIS N0012345678, how do I request CPT?"* The privacy note shows the name and SEVIS ID were removed before processing; the admin log shows `[NAME]` and `[SEVIS_ID]`.
4. Switch to "Prospective student". **Scholarships**: GPA 3.6, ACT 27 shows the President's, Dean's and Advantage awards with amounts.
5. **Programs**: search "data" to find the M.S. Data Science, then click *Ask about it*.
6. **Contacts**: type "reset my password" and the IT Help Desk is the best match.
7. **Getting started**: open the International graduate checklist and tick a step.
8. Ask something off-topic. It says it couldn't find the answer instead of guessing.
9. **/admin**: the knowledge monitor shows real conflicts on the university's own pages:
   - TOEFL minimum **71** (support FAQ) vs **79** (current apply page)
   - MBA **36** vs **30** credit hours
   - Online admission phone **601-968-5940** vs **601-968-8881**
   - 37 support FAQs last updated 1–2 years ago

## Validation: the 100-question test

`eval/questions.csv` has 100 realistic questions across every student type and service area, including
off-topic, privacy, immigration-risk and crisis cases. Each one lists the official page it should be answered
from and the expected behavior.

```bash
# with the backend running
python eval/run_eval.py --label "after crawl, Azure OpenAI"
```

The script writes `eval/results/<time>.md` (summary by category, every failure) and `<time>.csv` (every
answer, with empty `reviewer_grade` / `reviewer_notes` columns for a person to mark correct / partly / wrong).

**Baseline** (`eval/results/baseline-no-ai.md`): 100/100 with no AI key on the seed content. Treat that number
with care: I tuned the search while writing these questions, so this set is not independent. Before quoting
results to the university, add 30+ questions written by students or staff who haven't seen the system, run
the script again with the AI key on and the full crawl done, and have a person grade the answers.

## Known limits (be upfront about these in the demo)
- **Redaction is pattern-based.** A lowercase single first name with no surname ("i am priya") or a name with no introduction ("priya needs cpt") can get through. Real deployments should add the university's own data-loss-prevention tooling.
- **Answer verification is rule-based** unless `VERIFY_WITH_AI=true`. It catches wrong figures, wrong subjects, missing citations and promises the sources don't make, but it can't judge every paraphrase.
- **Rate and concurrency limits are per server process.** Running several API replicas needs a shared store (e.g. Redis) for exact limits; the daily AI cap is already shared through the database.
- **Not yet tested here:** a live AI provider (tested with a simulated OpenAI-compatible service) and a full crawl of belhaven.edu (tested with sample pages and PDFs).

## Tests
```bash
cd backend && python -m pytest -q
```
