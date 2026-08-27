import { useEffect, useState } from "react";
import { AdSlot } from "./components/AdSlot";
import { quotaLeft, streamRun, type RunEvent } from "./api";

const AGENTS = ["scout", "matcher", "writer", "critic", "interviewer"] as const;
type Agent = (typeof AGENTS)[number];

const BLURB: Record<Agent, string> = {
  scout: "Reads the posting",
  matcher: "Scores your CV",
  writer: "Drafts bullets + letter",
  critic: "Sends it back if it is vague",
  interviewer: "Builds your prep pack",
};

type Result = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export function App() {
  const [posting, setPosting] = useState("");
  const [cv, setCv] = useState("");
  const [running, setRunning] = useState(false);
  const [active, setActive] = useState<Agent | null>(null);
  const [passes, setPasses] = useState<Record<string, number>>({});
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");
  const [left, setLeft] = useState<number | null>(null);

  useEffect(() => {
    quotaLeft().then(setLeft).catch(() => setLeft(null));
  }, []);

  async function go() {
    setRunning(true);
    setResult(null);
    setError("");
    setPasses({});
    try {
      for await (const event of streamRun(posting, cv)) {
        handle(event);
      }
    } catch (e) {
      setError(String(e));
    }
    setActive(null);
    setRunning(false);
    quotaLeft().then(setLeft).catch(() => undefined);
  }

  function handle(event: RunEvent) {
    if (event.type === "start") {
      setActive(event.agent as Agent);
      setPasses((p) => ({ ...p, [event.agent]: (p[event.agent] ?? 0) + 1 }));
    } else if (event.type === "done") {
      setResult(event.result);
    } else if (event.type === "error") {
      setError(event.message);
    }
  }

  const ready = posting.trim().length >= 40 && cv.trim().length >= 40 && !running;

  return (
    <main>
      <header>
        <h1>GradPilot</h1>
        <p>Paste a posting and your CV. Five agents tailor the application and explain every change.</p>
        {left !== null && <p className="quota">{left} free runs left in this browser.</p>}
      </header>

      <section className="inputs">
        <label>
          Job posting
          <textarea value={posting} onChange={(e) => setPosting(e.target.value)} rows={10}
            placeholder="Paste the full posting, including the requirements list." />
        </label>
        <label>
          Your CV
          <textarea value={cv} onChange={(e) => setCv(e.target.value)} rows={10}
            placeholder="Paste your CV as plain text." />
        </label>
      </section>

      <button onClick={go} disabled={!ready}>
        {running ? "Running the graph…" : "Tailor my application"}
      </button>
      {!ready && !running && <p className="hint">Both boxes need at least 40 characters.</p>}
      {error && <p className="error">{error}</p>}

      <ol className="pipeline">
        {AGENTS.map((agent) => (
          <li key={agent} className={active === agent ? "on" : passes[agent] ? "done" : ""}>
            <strong>{agent}</strong>
            <span>{BLURB[agent]}</span>
            {(passes[agent] ?? 0) > 1 && <em>pass {passes[agent]}</em>}
          </li>
        ))}
      </ol>

      <AdSlot slot="1234567890" />

      {result && <Results result={result} />}
    </main>
  );
}

function Results({ result }: { result: Result }) {
  const critique = result.critique ?? {};
  return (
    <section className="results">
      <div className="card">
        <h2>Verdict</h2>
        <p className={result.approved ? "ok" : "warn"}>
          Critic score {critique.score} — {result.approved ? "approved" : "still weak"}
        </p>
        <ul>{(critique.notes ?? []).map((n: string) => <li key={n}>{n}</li>)}</ul>
      </div>

      <div className="card">
        <h2>Gaps to close</h2>
        <ul>
          {(result.matcher?.gaps ?? []).map((g: { requirement: string; advice: string }) => (
            <li key={g.requirement}><strong>{g.requirement}</strong>: {g.advice}</li>
          ))}
        </ul>
      </div>

      <div className="card">
        <h2>Tailored bullets</h2>
        <ul>{(result.draft?.bullets ?? []).map((b: string) => <li key={b}>{b}</li>)}</ul>
      </div>

      <div className="card">
        <h2>Cover letter</h2>
        <pre>{result.draft?.cover_letter}</pre>
      </div>

      <div className="card">
        <h2>Interview prep</h2>
        {(result.interviewer?.questions ?? []).map(
          (q: { question: string; why: string; star: Record<string, string> }) => (
            <details key={q.question}>
              <summary>{q.question}</summary>
              <p className="why">{q.why}</p>
              <ul>
                {Object.entries(q.star).map(([k, v]) => (
                  <li key={k}><strong>{k}</strong>: {v}</li>
                ))}
              </ul>
            </details>
          ),
        )}
      </div>
    </section>
  );
}
