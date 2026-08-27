import { useRef, useState } from 'react'
import { fetchSample, streamRun } from './api'
import AdSlot from './components/AdSlot'
import AgentTrace from './components/AgentTrace'
import Results from './components/Results'
import type { AgentName, RunResult, TraceEntry } from './types'

const AGENTS: AgentName[] = ['scout', 'matcher', 'writer', 'critic', 'interviewer']

export default function App() {
  const [jobPosting, setJobPosting] = useState('')
  const [cv, setCv] = useState('')
  const [targetRole, setTargetRole] = useState('')
  const [trace, setTrace] = useState<TraceEntry[]>([])
  const [result, setResult] = useState<RunResult | null>(null)
  const [error, setError] = useState('')
  const [quotaNote, setQuotaNote] = useState('')
  const [running, setRunning] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const ready = jobPosting.trim().length >= 40 && cv.trim().length >= 40

  async function loadSample() {
    try {
      const sample = await fetchSample()
      setJobPosting(sample.job_posting)
      setCv(sample.cv)
      setTargetRole(sample.target_role)
      setError('')
    } catch {
      setError('Could not reach the backend. Is it running on port 8000?')
    }
  }

  function stop() {
    abortRef.current?.abort()
    setRunning(false)
  }

  async function run() {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setRunning(true)
    setError('')
    setResult(null)
    setTrace([])

    try {
      for await (const event of streamRun(
        { job_posting: jobPosting, cv, target_role: targetRole },
        controller.signal,
      )) {
        if (event.type === 'quota') setQuotaNote(event.message)
        if (event.type === 'error') setError(event.message)
        if (event.type === 'agent_started') {
          setTrace((current) => [
            ...current,
            { agent: event.agent as AgentName, label: event.message, status: 'running' },
          ])
        }
        if (event.type === 'agent_finished') {
          setTrace((current) =>
            current.map((entry, index) =>
              index === current.length - 1 ? { ...entry, status: 'done', detail: event.message } : entry,
            ),
          )
        }
        if (event.type === 'run_finished' && event.data) {
          setResult(event.data as unknown as RunResult)
        }
      }
    } catch (caught) {
      if ((caught as Error).name !== 'AbortError') setError((caught as Error).message)
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="page">
      <header className="hero">
        <p className="hero__kicker">Five agents, one application</p>
        <h1>Stop sending the same CV to every job.</h1>
        <p className="hero__sub">
          Paste a posting and your CV. A scout, a matcher, a writer, a critic and an interviewer work through them
          together and hand back a tailored application plus the questions you are going to be asked.
        </p>
        <ul className="hero__agents">
          {AGENTS.map((agent) => (
            <li key={agent}>{agent}</li>
          ))}
        </ul>
      </header>

      <main className="layout">
        <section className="card">
          <div className="card__head">
            <h2>Your inputs</h2>
            <button type="button" className="btn btn--ghost btn--small" onClick={loadSample} disabled={running}>
              Load a sample
            </button>
          </div>

          <label className="field">
            <span>Job posting</span>
            <textarea
              value={jobPosting}
              onChange={(event) => setJobPosting(event.target.value)}
              placeholder="Paste the full posting, including the requirements section."
              rows={12}
              disabled={running}
            />
          </label>

          <label className="field">
            <span>Your CV</span>
            <textarea
              value={cv}
              onChange={(event) => setCv(event.target.value)}
              placeholder="Paste your CV as plain text. Projects and coursework count."
              rows={12}
              disabled={running}
            />
          </label>

          <label className="field">
            <span>Target role (optional)</span>
            <input
              value={targetRole}
              onChange={(event) => setTargetRole(event.target.value)}
              placeholder="Graduate Data Engineer"
              disabled={running}
            />
          </label>

          <div className="card__actions">
            <button type="button" className="btn" onClick={run} disabled={!ready || running}>
              {running ? 'Agents are working\u2026' : 'Run the crew'}
            </button>
            {running && (
              <button type="button" className="btn btn--ghost" onClick={stop}>
                Stop
              </button>
            )}
            {!ready && <span className="hint">Both boxes need at least a paragraph.</span>}
          </div>

          {quotaNote && <p className="quota">{quotaNote}</p>}
          {error && <p className="error">{error}</p>}

          <AdSlot slot="0987654321" />
        </section>

        <section className="card card--trace">
          <h2>What the crew is doing</h2>
          {trace.length === 0 && !running && (
            <p className="empty">
              Nothing running yet. Load the sample if you want to watch a full pass before pasting your own.
            </p>
          )}
          <AgentTrace entries={trace} />
        </section>
      </main>

      {result && <Results result={result} />}

      <footer className="footer">
        <p>
          GradPilot is a portfolio project. Nothing you paste is stored server side; runs are capped per browser so
          the free tier stays free.
        </p>
      </footer>
    </div>
  )
}
