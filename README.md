# GradPilot

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

## Paying for runs

Three tiers, in the order the code checks them:

1. **Your own key.** Paste an OpenAI, Anthropic or Gemini key in the UI. It is
   kept in `localStorage`, sent as a header per request, never written down
   server-side, and the free cap does not apply — the run is billed to you.
2. **Free runs.** Five per browser session, with a per-IP daily backstop.
3. **Paid credits.** RM10 for 20 runs through toyyibPay (FPX and selected
   e-wallets; an individual can register without an SSM company).

Checkout **refuses to open** unless `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`
are set, because the fallback credit store is in-process and a redeploy would
erase balances someone paid for. Create the table first:

```sql
create table credits (
  session text primary key,
  balance int not null default 0,
  updated_at timestamptz not null default now()
);
```

The payment callback never trusts the POST it receives — toyyibPay's callback is
forgeable, so the server calls `getBillTransactions` back and grants credits only
on what toyyibPay itself confirms, once per bill code.

## Monetisation hooks

`frontend/src/components/AdSlot.tsx` renders responsive ad units and no-ops
until `VITE_ADSENSE_CLIENT` is set, so ads never appear in development. Free
runs are capped per browser session in `backend/app/quota.py`; the cap is the
natural upgrade point for a paid tier.
