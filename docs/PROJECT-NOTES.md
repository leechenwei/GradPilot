# GradPilot — project notes

Working notes for the build: what the MVP claims, what is real today, what is
missing before it is a production AI system, where to host it, and how to talk
about it in an interview.

## 1. The MVP, in STAR form

**Situation.** A fresh graduate applies to 100+ roles. One generic CV goes to all
of them. Tailoring works, but it costs 40+ minutes per application, so nobody
does it. The result is silence.

**Task.** Cut the tailoring cost from 40 minutes to about one minute, without
inventing experience the candidate does not have. Fabricated CV content is worse
than a generic CV, so grounding is a hard requirement, not a nice-to-have.

**Action.** Five agents run as a graph with one back-edge:
scout parses the posting, matcher scores the CV against each requirement, writer
drafts bullets and a letter from CV facts only, critic scores the draft on
evidence and tone and *sends it back* when it is vague, interviewer builds a STAR
prep pack. The revision loop is bounded at 2 retries. The whole run streams over
SSE so the user watches each agent fire.

**Result.** A tailored application in about a minute, with the critic's reasons
shown, so the user learns the pattern instead of copy-pasting. Runs fully offline
in mock mode, so the demo never depends on an API key or a bill.

**The one sentence MVP.** *The critic loop.* Anything can call an LLM and print a
cover letter. The defensible part is that a second model refuses the first draft
and says why — that is the difference between a toy wrapper and a system with a
quality gate.

## 2. Is this "production AI"? No. Here is the honest gap table

| Layer | Today | Missing |
| --- | --- | --- |
| Frontend | React + Vite, SSE streaming, a11y pass, responsive, dark mode | Auth UI, saved runs, file upload (PDF CV) |
| Backend | FastAPI, bounded agent graph, SSE, provider seam | Retries, timeouts, structured logs, request IDs |
| Database | **None.** All state is in memory | Postgres: users, runs, drafts, feedback |
| Observability | **None** | Traces per agent (LangSmith / Langfuse / OTel), latency + error dashboards |
| AI usage monitoring | **None** | Tokens and cost per run, per user, per agent; budget alarms |
| Golden dataset | **None** | 30–50 (posting, CV) pairs with human-graded expected output |
| RAG | **Not applicable yet** — nothing is retrieved | See §3: this is the biggest honest gap |
| Evals | 7 behaviour tests, including "critic rejects then approves" | Ragas faithfulness/relevance, positive AND negative cases, CI gate |
| Scalability | Single process, in-memory quota | Stateless workers, Redis quota, queue for long runs |
| Performance | Mock run is instant; real run is 5–7 serial LLM calls | Parallelise scout+matcher, cache by posting hash, stream tokens |
| Security | Input length caps, per-IP daily cap, redacted upstream errors, no data stored | Real authn (the session id is client-supplied, so the per-session cap is a UX affordance, not a control), prompt-injection guard on pasted postings, PII handling policy |
| Usability | Streaming pipeline view, copy buttons, empty/error states | Onboarding sample, export to DOCX/PDF, run history |
| Maintainability | Typed, linted, CI on both halves, one LLM seam | Prompt versioning, ADRs, contract tests per agent |

Read that table as the roadmap, not as an apology. A portfolio project that names
its own gaps beats one that pretends there are none.

## 3. Where RAG actually belongs here

There is no retrieval today, and adding a vector DB just to say "RAG" would be
cargo cult. The honest hook is: **a company knowledge pack.** Retrieve the
employer's real posting archive, engineering blog, Glassdoor themes and product
docs, then ground the cover letter and the interview questions in them.

If that is built, the pieces the interviewer will ask about:

- **Parent-child chunking.** Embed small child chunks (a paragraph) for retrieval
  precision, but hand the model the parent chunk (the whole section) for context.
  It fixes the classic failure where a precise hit lacks the surrounding meaning.
- **Hybrid search + RRF.** BM25 catches exact tokens (`FastAPI`, `Kubernetes`),
  embeddings catch meaning ("ships fast" ≈ "weekly releases"). Reciprocal Rank
  Fusion merges the two ranked lists by `1/(k + rank)`, so neither scorer's
  absolute scale has to be normalised. Use `k=60` unless measurement says else.
- **Ragas.** Faithfulness (is every claim supported by retrieved context?),
  answer relevance, context precision and recall. LLM-as-judge, no human labels.
- **Positive and negative eval cases.** Positive: the CV genuinely matches, the
  writer must surface the evidence. Negative: the CV does *not* have the skill —
  the correct behaviour is to report a gap, not to invent experience. Negative
  cases are the ones that catch hallucination; most people only write positives.

## 4. Hosting

| Piece | Pick | Why |
| --- | --- | --- |
| Frontend | **Vercel** (or Cloudflare Pages) | Static build, free tier, deploys from GitHub on push |
| Backend | **Render** or **Fly.io** | Long-lived SSE streams survive; serverless functions often cut them off |
| Database | **Supabase** or **Neon** | Free Postgres, connection pooling |
| Secrets | Host env vars | Never in the Vite build — `VITE_*` is public by definition |
| Observability | **Langfuse** cloud free tier | Per-agent traces without running infrastructure |

Do not put the SSE backend on Vercel serverless. Streaming plus a per-invocation
timeout is a bad match, and the failure only shows up under a slow real model —
i.e. in the demo, in front of the interviewer.

## 5. Interview notes for a fresh-grad AI engineer

### Rounds, by company size

- **Startup (seed–Series B): 2–3 rounds**, often compressed into a day or two —
  founder/hiring-manager screen, a practical work sample, a final chat. Timeline
  2–4 weeks ([LoopCV][1], [FoundRole][2]).
- **SME / mid-size: ~3–4 rounds**, 4–6 weeks ([LoopCV][1]).
- **MNC: 4–6 rounds**, committee decision, formal competency rubric, 6–10 weeks
  ([LoopCV][1]). The 2026 loop typically runs recruiter screen → online
  assessment / technical phone screen → coding → system design → behavioural +
  hiring manager, with FAANG loops at 7–8 including a bar raiser
  ([Levelop][3], [Prepfully][4]). Final calls sit with a hiring committee, not
  one interviewer ([Prepfully][4]).

That matches the local MNC shape: HR → tech test → (optional) system design →
hiring manager 1 → hiring manager 2 → culture fit.

**The practical advice that matters most:** the CV is the only gate you can move
before a human ever talks to you. A tailored CV gets you the HR call; a generic
one gets ghosted. Everything downstream is unreachable until that first gate
opens. (That is the product thesis of this repo, which is a good thing to say out
loud in the interview.)

### What the technical round asks

Mostly SE-shaped, not research-shaped: SQL, pandas/dataframe manipulation,
LeetCode-style data structures, and practical front-end/system trivia such as
debouncing and throttling. For AI roles specifically, 2026 interviews are
60%+ GenAI — RAG end-to-end design, chunking strategy, evaluation metrics and
production trade-offs are the most heavily tested topic ([CoPrep][5],
[Let's Data Science][6]).

### Hiring-manager questions, and how to answer them

**"How do you know the AI is accurate? What metrics?"**
Name the layer. Retrieval: context precision and recall. Generation:
faithfulness (every claim traceable to context), answer relevance, completeness —
the three that catch most production failure modes ([Braintrust][7]).
Task-level: a golden dataset with human-graded expected outputs, run in CI so a
prompt change that regresses quality fails the build.

**"Do you judge every output, or trust it blindly?"**
Neither. Three tiers: automated LLM-judge on every run for cheap checks
(faithfulness, format), human review on a sample, and a hard rule-based gate on
anything irreversible. In this repo the critic agent *is* tier one, and it can
reject — a judge that can only score and never block is decoration.

**"How do you prevent hallucination?"**
Ground it, constrain it, verify it. Ground: the writer's prompt forbids facts
absent from the CV. Constrain: JSON schema output, so the shape cannot drift.
Verify: a second model checks each claim against the source, and in production
you track no-retrieval rate and hallucination rate as live metrics
([Braintrust][7]). Then, crucially, design the *fallback* — say "I could not find
evidence for this" instead of inventing it. Negative eval cases are how you prove
the fallback fires.

**"What breaks first at high traffic?"**
Not your code — the provider rate limit and the token bill. Then latency, because
the agents are serial: five calls means five round trips. Fixes in order:
parallelise the independent agents, cache by input hash, queue long runs and
stream partials, degrade to a smaller model under load, and make the quota real
(Redis, not a process dict).

**"How do you automate a production AI process?"**
CI runs the golden-dataset evals on every prompt change; traces stream to
Langfuse; cost and latency alarms per agent; canary a new prompt on 5% of traffic
and compare eval scores before rollout; keep prompts versioned in a store, not
hardcoded in a deploy ([TestMu][8]).

**"What comes after building the agent?"**
Evals, observability, cost control, and a feedback loop that turns real failures
into new golden cases. Building the agent is roughly 20% of the work.

**"How do you avoid duplicate agents — one per feature?"**
Separate the *capability* from the *task*. One agent runtime with a tool
registry, a prompt/policy per task, and shared memory and eval harness. New
feature = a new prompt plus tool permissions, not a new codebase. The test for
whether you got it right: adding a feature should not add a deployment.

[1]: https://www.loopcv.pro/guides/how-many-interview-rounds-is-normal/
[2]: https://www.foundrole.com/blog/how-to-get-hired-at-startup-complete-guide
[3]: https://levelop.dev/blog/the-complete-software-engineer-interview-process-in-2026-what-to-expect-at-every
[4]: https://prepfully.com/interview-guides/software-engineer-interview-rubric-2026
[5]: https://www.coprep.ai/blog/top-ai-engineer-interview-questions-in-2026-llms-rag-agents-and-langchain
[6]: https://letsdatascience.com/blog/50-llm-and-ai-engineer-interview-questions-for-2026
[7]: https://www.braintrust.dev/articles/ai-hallucination-evaluations-metrics-methods-2026
[8]: https://www.testmuai.com/blog/llm-evaluation/
