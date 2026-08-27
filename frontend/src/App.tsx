import { useEffect, useRef, useState } from "react";
import { AdSlot } from "./components/AdSlot";
import {
  AlertIcon, CheckIcon, CopyIcon, CriticIcon, InterviewerIcon, MatcherIcon,
  LinkIcon, ScoutIcon, SparkIcon, UploadIcon, WriterIcon,
} from "./components/icons";
import { extractFile, importPosting, quotaLeft, streamRun, type RunEvent } from "./api";
import { SAMPLE_CV, SAMPLE_POSTING } from "./sample";

const MIN_CHARS = 40;

const STAGES = [
  { id: "scout", label: "Scout", blurb: "Reads the posting", Icon: ScoutIcon },
  { id: "matcher", label: "Matcher", blurb: "Scores your CV against it", Icon: MatcherIcon },
  { id: "writer", label: "Writer", blurb: "Drafts bullets and the letter", Icon: WriterIcon },
  { id: "critic", label: "Critic", blurb: "Sends vague drafts back", Icon: CriticIcon },
  { id: "interviewer", label: "Interviewer", blurb: "Builds the prep pack", Icon: InterviewerIcon },
] as const;

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Result = Record<string, any>;

export function App() {
  const [posting, setPosting] = useState("");
  const [cv, setCv] = useState("");
  const [running, setRunning] = useState(false);
  const [active, setActive] = useState<string | null>(null);
  const [passes, setPasses] = useState<Record<string, number>>({});
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");
  const [left, setLeft] = useState<number | null>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    quotaLeft().then(setLeft).catch(() => setLeft(null));
  }, []);

  const ready = posting.trim().length >= MIN_CHARS && cv.trim().length >= MIN_CHARS;

  async function go() {
    setRunning(true);
    setResult(null);
    setError("");
    setPasses({});
    try {
      for await (const event of streamRun(posting, cv)) apply(event);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setActive(null);
    setRunning(false);
    quotaLeft().then(setLeft).catch(() => undefined);
    resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function apply(event: RunEvent) {
    if (event.type === "start") {
      setActive(event.agent);
      setPasses((p) => ({ ...p, [event.agent]: (p[event.agent] ?? 0) + 1 }));
    } else if (event.type === "done") {
      setResult(event.result);
    } else if (event.type === "error") {
      setError(event.message);
    }
  }

  return (
    <>
      <a className="skip" href="#main">Skip to content</a>
      <div className="shell">
        <header className="hero">
          <span className="eyebrow"><SparkIcon /> Five agents, one minute</span>
          <h1>Stop sending the same CV to every job.</h1>
          <p>
            Paste a posting and your CV. GradPilot finds the gaps, rewrites your bullets,
            drafts the cover letter and builds your interview prep — and shows you why it
            changed each line.
          </p>
        </header>

        <main id="main">
          <section className="card" aria-labelledby="input-heading">
            <h2 id="input-heading">Your inputs</h2>
            <div className="fields">
              <Field
                id="posting" label="Job posting" value={posting} onChange={setPosting}
                placeholder="Paste the full posting, including the requirements list."
                help="The whole ad works better than a summary — the Scout reads the requirements verbatim."
              >
                <UrlImport onText={setPosting} />
              </Field>
              <Field
                id="cv" label="Your CV" value={cv} onChange={setCv}
                placeholder="Paste your CV as plain text."
                help="PDF or plain text. Nothing is stored — the file is parsed in memory and dropped."
              >
                <FileImport onText={setCv} />
              </Field>
            </div>

            <div className="actions">
              <button onClick={go} disabled={!ready || running} aria-busy={running}>
                {running ? "Running the agents…" : "Tailor my application"}
              </button>
              <button
                className="ghost"
                disabled={running}
                onClick={() => {
                  setPosting(SAMPLE_POSTING);
                  setCv(SAMPLE_CV);
                }}
              >
                Fill a sample
              </button>
              {!ready && !running && (
                <span className="help">Both boxes need at least {MIN_CHARS} characters.</span>
              )}
              {left !== null && (
                <span className="quota">{left} free {left === 1 ? "run" : "runs"} left</span>
              )}
            </div>

            {error && (
              <p className="banner error" role="alert"><AlertIcon /> {error}</p>
            )}
          </section>

          <section className="card" aria-labelledby="pipeline-heading">
            <h2 id="pipeline-heading">Pipeline</h2>
            <ol className="pipeline" aria-live="polite">
              {STAGES.map(({ id, label, blurb, Icon }) => {
                const runs = passes[id] ?? 0;
                const state = active === id ? "active" : runs ? "done" : "";
                return (
                  <li key={id} className={`stage ${state} ${runs > 1 ? "revised" : ""}`}>
                    <span className={`dot ${active === id ? "spin" : ""}`}>
                      {runs && active !== id ? <CheckIcon /> : <Icon />}
                    </span>
                    <span>
                      <b>{label}</b>
                      <small>{blurb}</small>
                    </span>
                    <span className="tag">
                      {active === id ? "Running" : runs > 1 ? `${runs} passes` : runs ? "Done" : ""}
                    </span>
                  </li>
                );
              })}
            </ol>
            {passes.critic > 1 && (
              <p className="banner">
                <AlertIcon />
                The critic rejected the first draft and sent it back. That loop is the point —
                it is what stops the letter reading like a template.
              </p>
            )}
          </section>

          <AdSlot slot="1234567890" />

          <div ref={resultsRef}>{result && <Results result={result} />}</div>
        </main>

        <footer>
          Built as a portfolio project. Runs offline in mock mode — no key, no data leaves the box.
        </footer>
      </div>
    </>
  );
}

function Field(props: {
  id: string; label: string; value: string; placeholder: string; help: string;
  onChange: (v: string) => void; children?: React.ReactNode;
}) {
  const short = props.value.length > 0 && props.value.trim().length < MIN_CHARS;
  return (
    <div className="field">
      <div className="field-head">
        <label htmlFor={props.id}>{props.label}</label>
        <span className={`count ${short ? "short" : ""}`}>
          {props.value.length} chars{short ? ` — need ${MIN_CHARS}` : ""}
        </span>
      </div>
      <textarea
        id={props.id}
        value={props.value}
        placeholder={props.placeholder}
        aria-describedby={`${props.id}-help`}
        onChange={(e) => props.onChange(e.target.value)}
      />
      {props.children}
      <p className="help" id={`${props.id}-help`}>{props.help}</p>
    </div>
  );
}

/** Pull a public job ad in by URL. Big boards block bots, so failure is normal here. */
function UrlImport({ onText }: { onText: (text: string) => void }) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");

  async function fetchIt() {
    setBusy(true);
    setProblem("");
    try {
      onText(await importPosting(url));
    } catch (e) {
      setProblem(e instanceof Error ? e.message : String(e));
    }
    setBusy(false);
  }

  return (
    <div className="tool">
      <div className="tool-row">
        <input
          type="url"
          inputMode="url"
          aria-label="Job posting URL"
          placeholder="https://company.com/careers/data-engineer"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <button className="ghost tiny" onClick={fetchIt} disabled={busy || url.length < 8}>
          <LinkIcon /> {busy ? "Fetching…" : "Fetch"}
        </button>
      </div>
      {problem && <p className="help problem" role="status">{problem}</p>}
    </div>
  );
}

/** Read a PDF or text CV in the browser and hand the extracted text back. */
function FileImport({ onText }: { onText: (text: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const [name, setName] = useState("");

  return (
    <div className="tool">
      <div className="tool-row">
        <label className="filepick">
          <UploadIcon /> {busy ? "Reading…" : "Upload PDF"}
          <input
            type="file"
            accept=".pdf,.txt,.md"
            disabled={busy}
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              setBusy(true);
              setProblem("");
              setName(file.name);
              try {
                onText(await extractFile(file));
              } catch (err) {
                setProblem(err instanceof Error ? err.message : String(err));
              }
              setBusy(false);
              e.target.value = "";
            }}
          />
        </label>
        {name && !problem && <span className="help">{name}</span>}
      </div>
      {problem && <p className="help problem" role="status">{problem}</p>}
    </div>
  );
}

function CopyButton({ text, what }: { text: string; what: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      className="ghost tiny"
      onClick={() => {
        navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          window.setTimeout(() => setCopied(false), 2500);
        });
      }}
      aria-label={`Copy ${what}`}
    >
      {copied ? <CheckIcon /> : <CopyIcon />} {copied ? "Copied" : "Copy"}
    </button>
  );
}

function Results({ result }: { result: Result }) {
  const critique = result.critique ?? {};
  const score = Number(critique.score ?? 0);
  const bullets: string[] = result.draft?.bullets ?? [];
  const letter: string = result.draft?.cover_letter ?? "";

  return (
    <section className="results" aria-label="Results">
      <div className="card">
        <h2>Critic verdict</h2>
        <div className="verdict">
          <span className="score">{score.toFixed(2)}</span>
          <span className="meter"><i style={{ width: `${Math.round(score * 100)}%` }} /></span>
          <span className={`pill ${result.approved ? "ok" : "warn"}`}>
            {result.approved ? <CheckIcon /> : <AlertIcon />}
            {result.approved ? "Approved" : "Still weak"}
          </span>
        </div>
        <ul className="list" style={{ marginTop: "1rem" }}>
          {(critique.notes ?? []).map((n: string) => <li key={n}>{n}</li>)}
        </ul>
      </div>

      <div className="card">
        <h2>Gaps to close</h2>
        <ul className="list">
          {(result.matcher?.gaps ?? []).map((g: { requirement: string; advice: string }) => (
            <li key={g.requirement} className="gap">
              <b>{g.requirement}</b>
              <span>{g.advice}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="card">
        <div className="card-head">
          <h2>Tailored CV bullets</h2>
          <CopyButton text={bullets.join("\n")} what="the tailored bullets" />
        </div>
        <ul className="list">{bullets.map((b) => <li key={b}>{b}</li>)}</ul>
      </div>

      <div className="card">
        <div className="card-head">
          <h2>Cover letter</h2>
          <CopyButton text={letter} what="the cover letter" />
        </div>
        <pre className="letter">{letter}</pre>
      </div>

      <div className="card">
        <h2>Interview prep</h2>
        {(result.interviewer?.questions ?? []).map(
          (q: { question: string; why: string; star: Record<string, string> }) => (
            <details key={q.question}>
              <summary>{q.question}</summary>
              <p className="why">{q.why}</p>
              <ul className="star">
                {Object.entries(q.star).map(([k, v]) => (
                  <li key={k}><b>{k}</b><span>{v}</span></li>
                ))}
              </ul>
            </details>
          ),
        )}
      </div>
    </section>
  );
}
