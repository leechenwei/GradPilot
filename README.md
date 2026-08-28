# GradPilot

[![CI](https://github.com/leechenwei/GradPilot/actions/workflows/ci.yml/badge.svg)](https://github.com/leechenwei/GradPilot/actions)
[![Licence: MIT](https://img.shields.io/badge/licence-MIT-blue.svg)](LICENSE)

**Live demo:** https://grad-pilot-inky.vercel.app — bring your own model key
(OpenRouter has free models).

A multi-agent AI copilot that helps fresh graduates turn a job posting into a
tailored application: gap analysis, rewritten CV bullets, a cover letter, and an
interview prep pack.

Five agents run as a graph with a critic-driven revision loop:

```
Scout ──> Matcher ──> Writer ──> Critic ──(score < threshold)──> Writer
                          │                     │
                          └────> Interviewer <──┘ (on approval)
```

| Agent | Job |
| --- | --- |
| `scout` | Parses the raw posting into structured requirements + company signals |
| `matcher` | Scores the CV against each requirement, finds strengths and gaps |
| `writer` | Produces tailored CV bullets and a cover letter grounded in the CV |
| `critic` | Scores the draft on evidence, specificity and tone; requests revisions |
| `interviewer` | Builds likely questions with STAR answer scaffolds |

## Why it exists

Fresh grads apply to hundreds of roles with one generic CV. Tailoring works, but
it takes 40+ minutes per application. GradPilot does it in about a minute and
explains *why* each change was made, so the user learns instead of just
copy-pasting.

## Tech stack

| Layer | Choice | Why |
| --- | --- | --- |
| Frontend | React 18 + TypeScript, Vite | Small, fast, no framework tax for a single page |
| Styling | Plain CSS with custom properties | ~10 kB, light/dark from one token set, no build plugin |
| Icons | Inline SVG (Lucide paths) | One icon set, no runtime dependency |
| Backend | FastAPI + Uvicorn (Python 3.11) | Streaming responses and typed request models |
| Streaming | Server-Sent Events | One-way stream, plain HTTP, no WebSocket to operate |
| Agents | Plain Python functions and a loop | Five nodes and one back-edge do not need a graph framework |
| Models | OpenAI, Anthropic, Gemini, OpenRouter over `httpx` | One `complete()` seam, no vendor SDKs |
| PDF | `pypdf` | Pure Python, parses in memory, nothing written to disk |
| HTML | `html.parser` from the stdlib | No scraping dependency for job-ad text |
| PWA | Hand-written manifest + service worker | ~40 lines, no plugin, no generated bundle |
| Tests | pytest, ruff, mypy, ESLint, tsc | Both halves gated in CI |
| Hosting | Vercel (frontend) + Render (API) | Render keeps SSE streams alive; serverless cuts them |

No LangChain, no LangGraph, no vector database, no ORM, no CSS framework, no state
library. Each is a deliberate omission, not an oversight — the project is small
enough that the standard library and one HTTP client cover it.

## What it does

- **Five agents with a real quality gate.** The critic scores each draft on
  evidence and tone and sends weak ones back to the writer, bounded at two
  revisions. The best-scoring draft wins, not the last one written.
- **Streams as it runs.** Each agent lights up over SSE; a failed agent is marked
  failed, not ticked green.
- **Grounded by construction.** The writer may only use facts present in the CV.
  With no model configured the API returns `412` instead of canned text, because
  invented experience sent to a real employer is worse than no output.
- **Reads real inputs.** PDF CV upload, Greenhouse and Lever postings through
  their public JSON APIs, ordinary careers pages by URL, and a bookmarklet for
  the boards that block servers.
- **Installable.** Manifest, icons and a shell-only service worker; the API is
  never cached, so a stale result cannot be shown as a fresh one.

## Architecture

```
Browser ──POST /api/run──> FastAPI ──> graph.run() ──> llm.complete() ──> provider
   ^                          │            │
   └────── SSE events ────────┘            └── scout → matcher → writer ⇄ critic → interviewer
```

`llm.py` is the only file that knows a provider exists. `graph.py` is the only
file that knows the agent order. Adding a provider is one branch; changing the
loop touches one file.

## Running locally

Backend:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

Upload a PDF CV or fetch a public job ad by URL from the same screen: the
backend extracts the text and hands the agents the same plain text a paste would
have produced. Postings hosted on Greenhouse or Lever are read through their public JSON APIs.
Big job boards (LinkedIn, Indeed, JobStreet, Seek) block server fetches behind a
login, so those fail fast and point at the bookmarklet instead: it reads the ad
in the user's own logged-in tab and hands the text over in the URL fragment,
which never reaches a server.

**A run needs a real model.** With no key configured and none supplied by the
user, `/api/run` answers `412` and the UI disables the button — canned text must
never leave the building dressed as someone's job application. Mock replies still
back the test suite and local UI work, behind an explicit opt-in:

```bash
export GRADPILOT_ALLOW_MOCK=1   # tests and local UI work only
```

OpenRouter works too, and has free models. Measured on a full run of this graph
(9 calls including the revision loop), August 2026:

| Free model | Result |
| --- | --- |
| `nvidia/nemotron-3-super-120b-a12b:free` | works, ~130 s, best structure — the default |
| `minimax/minimax-m3:free` | works, ~107 s, wordier letters |
| `minimax/minimax-m2.7:free` | works, but ~272 s |
| `z-ai/glm-5.2:free`, `google/gemma-4-*:free` | 429 — busy most of the time |
| `thinkingmachines/inkling:free` | 403 — agentic harnesses only |

Free ids rotate and the endpoints are heavily shared, so treat any of them as
best-effort and let users name their own model in the UI.

Set one of the following to use a real model:

```bash
export GRADPILOT_LLM_PROVIDER=openai   # openai | anthropic | gemini | mock
export OPENAI_API_KEY=sk-...
```

## Tests

```bash
cd backend && pytest && ruff check . && mypy app
```

## Bring your own key

GradPilot is public as a **bring-your-own-key** tool. Paste an OpenAI, Anthropic,
Gemini or OpenRouter key in the UI and the run is billed to you. The key is kept
in `localStorage`, sent as a header per request, and never stored or logged
server-side. A full run is about five model calls, or nine when the critic sends
a draft back.

OpenRouter has free models, so the whole thing can cost nothing. Measured on a
full run of this graph, August 2026:

| Free model | Result |
| --- | --- |
| `nvidia/nemotron-3-super-120b-a12b:free` | works, ~130 s, best structure — the default |
| `minimax/minimax-m3:free` | works, ~107 s, wordier letters |
| `minimax/minimax-m2.7:free` | works, but ~272 s |
| `z-ai/glm-5.2:free`, `google/gemma-4-*:free` | 429 — busy most of the time |

Free ids rotate and the endpoints are shared, so treat any of them as
best-effort; the UI lets a user name their own model.

There is also a dormant credit path (`app/credits.py`, `app/payments.py`) for a
paid tier later. It stays switched off — checkout returns 503 — until a durable
credit store is configured, because credits a redeploy would erase are worse than
no credits at all.

## Contributing

Issues and pull requests are welcome. Both halves are gated in CI, so run them
before opening a PR:

```bash
cd backend && ruff check . && mypy app && pytest -q
cd frontend && npm run lint && npm run typecheck && npm run build
```

Two house rules, both visible throughout the code:

1. **No canned output reaches a user.** Mock replies exist for tests only.
2. **Anything touching money, a key or a trust boundary gets a test.**

## Monetisation hooks

`frontend/src/components/AdSlot.tsx` renders responsive ad units and no-ops
until `VITE_ADSENSE_CLIENT` is set, so ads never appear in development. Free
runs are capped per browser session in `backend/app/quota.py`, with a per-IP
daily backstop, since the session id is client-supplied.

## Licence

MIT — see [LICENSE](LICENSE).
