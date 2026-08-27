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

With no API key set the backend runs in **mock mode**: the full agent graph
executes with deterministic canned model responses, so the UI, streaming and
revision loop are fully demoable offline. Set one of the following to use a real
model:

```bash
export GRADPILOT_LLM_PROVIDER=openai   # openai | anthropic | gemini | mock
export OPENAI_API_KEY=sk-...
```

## Tests

```bash
cd backend && pytest && ruff check . && mypy app
```

## Monetisation hooks

`frontend/src/components/AdSlot.tsx` renders responsive ad units and no-ops
until `VITE_ADSENSE_CLIENT` is set, so ads never appear in development. Free
runs are capped per browser session in `backend/app/quota.py`; the cap is the
natural upgrade point for a paid tier.
