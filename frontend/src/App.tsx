import { useEffect, useRef, useState } from "react";
import { AdSlot } from "./components/AdSlot";
import {
  AlertIcon, CheckIcon, CopyIcon, CriticIcon, InterviewerIcon, MatcherIcon,
  LinkIcon, ScoutIcon, SparkIcon, UploadIcon, WriterIcon,
} from "./components/icons";
import {
  extractFile, importPosting, readKey, saveKey, startCheckout, streamRun, wallet,
  type RunEvent, type Wallet,
} from "./api";
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
  const [failed, setFailed] = useState<string | null>(null);
  const [money, setMoney] = useState<Wallet | null>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  const refreshWallet = () => wallet().then(setMoney).catch(() => setMoney(null));

  useEffect(() => {
    refreshWallet();
  }, []);

  // The bookmarklet hands the posting over in the URL fragment. A fragment is never
  // sent to a server, so the ad text stays in the browser even in transit.
  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.slice(1));
    const imported = params.get("posting");
    if (imported) {
      setPosting(imported);
      history.replaceState(null, "", window.location.pathname);
    }
  }, []);

  // No model and no key means nothing can be written. Say so before the click, not after.
  const needsKey = money !== null && !money.model_ready && !readKey().key;
  const ready =
    posting.trim().length >= MIN_CHARS && cv.trim().length >= MIN_CHARS && !needsKey;

  async function go() {
    setRunning(true);
    setResult(null);
    setError("");
    setFailed(null);
    setPasses({});
    try {
      for await (const event of streamRun(posting, cv)) apply(event);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setActive(null);
    setRunning(false);
    refreshWallet();
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
      // The agent that was mid-flight is the one that broke. Do not tick it green.
      setActive((current) => {
        setFailed(current);
        return null;
      });
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
              {!ready && !running && !needsKey && (
                <span className="help">Both boxes need at least {MIN_CHARS} characters.</span>
              )}
              {money && <Wallet money={money} />}
            </div>

            {error && (
              <p className="banner error" role="alert"><AlertIcon /> {error}</p>
            )}

            {needsKey && (
              <p className="banner" role="status">
                <AlertIcon />
                This demo runs on your own API key. Paste one below and the agents write with
                the model you choose, billed to you — about US$0.01 a run. Nothing is generated
                without a key: an application built from canned text is worse than none.
              </p>
            )}

            <KeyBox onChange={refreshWallet} open={needsKey} />
          </section>

          <section className="card" aria-labelledby="pipeline-heading">
            <h2 id="pipeline-heading">Pipeline</h2>
            <ol className="pipeline" aria-live="polite">
              {STAGES.map(({ id, label, blurb, Icon }) => {
                const runs = passes[id] ?? 0;
                const broke = failed === id;
                const state = broke ? "failed" : active === id ? "active" : runs ? "done" : "";
                return (
                  <li key={id} className={`stage ${state} ${runs > 1 ? "revised" : ""}`}>
                    <span className={`dot ${active === id ? "spin" : ""}`}>
                      {broke ? <AlertIcon /> : runs && active !== id ? <CheckIcon /> : <Icon />}
                    </span>
                    <span>
                      <b>{label}</b>
                      <small>{blurb}</small>
                    </span>
                    <span className="tag">
                      {broke
                        ? "Failed"
                        : active === id
                          ? "Running"
                          : runs > 1
                            ? `${runs} passes`
                            : runs
                              ? "Done"
                              : ""}
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
          Built as a portfolio project. Runs on the model key you supply — your CV and the
          posting go to that provider and nowhere else, and nothing is stored here.
        </footer>
      </div>
    </>
  );
}

function Wallet({ money }: { money: Wallet }) {
  const { key } = readKey();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");

  if (key) return <span className="quota">Unlimited — billed to your own key</span>;

  const left = money.remaining + money.credits;
  return (
    <span className="quota">
      {left} {left === 1 ? "run" : "runs"} left
      {money.credits > 0 && ` (${money.credits} paid)`}
      {money.can_buy && left <= 2 && (
        <>
          {" · "}
          <button
            className="ghost tiny"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                window.location.href = await startCheckout();
              } catch (e) {
                setProblem(e instanceof Error ? e.message : String(e));
                setBusy(false);
              }
            }}
          >
            Buy {money.package.runs} runs — {money.package.price}
          </button>
        </>
      )}
      {problem && <span className="help problem"> {problem}</span>}
    </span>
  );
}

/** Bring your own key: the run is billed to the user, so the server pays nothing. */
function KeyBox({ onChange, open }: { onChange: () => void; open?: boolean }) {
  const saved = readKey();
  const [provider, setProvider] = useState(saved.provider);
  const [key, setKey] = useState(saved.key);
  const [model, setModel] = useState(saved.model);

  return (
    <details className="tip keybox" open={open}>
      <summary>{saved.key ? "Using your own API key" : "Use your own API key (unlimited runs)"}</summary>
      <p className="help">
        Paste a key and every run is billed to your own account. The key stays in this
        browser, rides along with each request, and is never written down on the server.
        A full run is about five model calls — roughly US$0.01 on a small model.
      </p>
      <p className="help">
        Get a key:{" "}
        <a href="https://platform.openai.com/api-keys" target="_blank" rel="noreferrer">OpenAI</a>
        {" · "}
        <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noreferrer">
          Anthropic
        </a>
        {" · "}
        <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer">Gemini</a>
        {" · "}
        <a href="https://openrouter.ai/keys" target="_blank" rel="noreferrer">
          OpenRouter (has free models)
        </a>
      </p>
      <div className="tool-row">
        <select
          aria-label="Model provider"
          value={provider}
          onChange={(e) => {
            setProvider(e.target.value);
            saveKey(e.target.value, key, model);
            onChange();
          }}
        >
          <option value="openai">OpenAI</option>
          <option value="anthropic">Anthropic</option>
          <option value="gemini">Gemini</option>
          <option value="openrouter">OpenRouter (free models)</option>
        </select>
        <input
          type="password"
          aria-label="API key"
          placeholder="sk-…"
          value={key}
          onChange={(e) => {
            setKey(e.target.value);
            saveKey(provider, e.target.value.trim(), model.trim());
          }}
          onBlur={onChange}
        />
        {key && (
          <button
            className="ghost tiny"
            onClick={() => {
              setKey("");
              saveKey(provider, "", model);
              onChange();
            }}
          >
            Forget key
          </button>
        )}
      </div>
      {provider === "openrouter" && (
        <div className="tool-row">
          <input
            aria-label="Model id"
            placeholder="nvidia/nemotron-3-super-120b-a12b:free"
            value={model}
            onChange={(e) => {
              setModel(e.target.value);
              saveKey(provider, key.trim(), e.target.value.trim());
            }}
          />
          <span className="help">
            Free ids rotate — copy one from{" "}
            <a href="https://openrouter.ai/models?max_price=0" target="_blank" rel="noreferrer">
              openrouter.ai/models
            </a>
            . Blank uses the default.
          </span>
        </div>
      )}
    </details>
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
          placeholder="https://boards.greenhouse.io/… or a company careers page"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <button className="ghost tiny" onClick={fetchIt} disabled={busy || url.length < 8}>
          <LinkIcon /> {busy ? "Fetching…" : "Fetch"}
        </button>
      </div>
      {problem && <p className="help problem" role="status">{problem}</p>}
      <Bookmarklet />
    </div>
  );
}

/** The walled boards block servers, not people. This runs in the user's own tab. */
function Bookmarklet() {
  const ref = useRef<HTMLAnchorElement>(null);

  useEffect(() => {
    const app = `${window.location.origin}${window.location.pathname}`;
    const code =
      "javascript:(function(){var s=String(window.getSelection());" +
      "var t=s.length>200?s:(document.querySelector('main')||document.body).innerText;" +
      `window.open('${app}#posting='+encodeURIComponent(t.slice(0,18000)),'_blank');})()`;
    // Set it after mount: React strips javascript: hrefs written through JSX.
    ref.current?.setAttribute("href", code);
  }, []);

  return (
    <details className="tip">
      <summary>LinkedIn, JobStreet or Indeed?</summary>
      <p className="help">
        Those sites block servers from reading them, so the fetch above will not work.
        Drag this button to your bookmarks bar, open the job ad, and click it — it reads
        the page in <em>your</em> browser, where you are already logged in, and sends the
        text back here. Select part of the page first to send only that.
      </p>
      <a className="bookmarklet" ref={ref} href="#" onClick={(e) => e.preventDefault()}>
        Send to GradPilot
      </a>
    </details>
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

const TABS = [
  { id: "verdict", label: "Critic verdict" },
  { id: "gaps", label: "Gaps to close" },
  { id: "bullets", label: "CV bullets" },
  { id: "letter", label: "Cover letter" },
  { id: "prep", label: "Interview prep" },
] as const;

function Results({ result }: { result: Result }) {
  const [tab, setTab] = useState<string>("verdict");
  const critique = result.critique ?? {};
  const score = Number(critique.score ?? 0);
  const bullets: string[] = result.draft?.bullets ?? [];
  const letter: string = result.draft?.cover_letter ?? "";
  const role: string = result.scout?.role ?? "";
  const company: string = result.scout?.company ?? "";

  // Arrow keys move between tabs: a tablist that only responds to clicks is broken
  // for keyboard users, and this is the main navigation of the whole result.
  function onKey(event: React.KeyboardEvent) {
    const index = TABS.findIndex((t) => t.id === tab);
    if (event.key === "ArrowRight") setTab(TABS[(index + 1) % TABS.length].id);
    if (event.key === "ArrowLeft") setTab(TABS[(index - 1 + TABS.length) % TABS.length].id);
  }

  return (
    <section className="results" aria-label="Results">
      <header className="result-head">
        <div>
          <h2>{role || "Your tailored application"}</h2>
          {company && <p className="sub">for {company}</p>}
        </div>
        <span className={`pill ${result.approved ? "ok" : "warn"}`}>
          {result.approved ? <CheckIcon /> : <AlertIcon />}
          {result.approved ? "Approved" : "Best of " + (result.passes ?? 1) + " drafts"}
        </span>
      </header>

      <div className="tabs" role="tablist" aria-label="Result sections" onKeyDown={onKey}>
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            tabIndex={tab === t.id ? 0 : -1}
            className={`tab ${tab === t.id ? "on" : ""}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="card panel" role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "verdict" && (
          <>
            <div className="verdict">
              <span className="score">{score.toFixed(2)}</span>
              <span className="meter"><i style={{ width: `${Math.round(score * 100)}%` }} /></span>
            </div>
            <ul className="list">
              {(critique.notes ?? []).map((n: string) => <li key={n}>{n}</li>)}
            </ul>
          </>
        )}

        {tab === "gaps" && (
          <ul className="list">
            {(result.matcher?.gaps ?? []).map((g: { requirement: string; advice: string }) => (
              <li key={g.requirement} className="gap">
                <b>{g.requirement}</b>
                <span>{g.advice}</span>
              </li>
            ))}
          </ul>
        )}

        {tab === "bullets" && (
          <>
            <div className="card-head">
              <span className="help">Paste these over the matching lines in your CV.</span>
              <CopyButton text={bullets.join("\n")} what="the tailored bullets" />
            </div>
            <ul className="list">{bullets.map((b) => <li key={b}>{b}</li>)}</ul>
          </>
        )}

        {tab === "letter" && (
          <>
            <div className="card-head">
              <span className="help">
                {letter.split(/\s+/).filter(Boolean).length} words
              </span>
              <CopyButton text={letter} what="the cover letter" />
            </div>
            <pre className="letter">{letter}</pre>
          </>
        )}

        {tab === "prep" && (
          <>
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
          </>
        )}
      </div>
    </section>
  );
}
