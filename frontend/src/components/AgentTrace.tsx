import type { TraceEntry } from '../types'

const AGENT_BLURB: Record<string, string> = {
  scout: 'Reads the posting and pulls out what is actually required',
  matcher: 'Scores your CV against every requirement, with evidence',
  writer: 'Rewrites your bullets and drafts the cover letter',
  critic: 'Reviews the draft and sends it back if it is not good enough',
  interviewer: 'Builds the question pack you will actually be asked',
}

export default function AgentTrace({ entries }: { entries: TraceEntry[] }) {
  if (entries.length === 0) return null

  return (
    <ol className="trace">
      {entries.map((entry, index) => (
        <li key={`${entry.agent}-${index}`} className={`trace__item trace__item--${entry.status}`}>
          <span className="trace__dot" aria-hidden />
          <div>
            <p className="trace__agent">
              {entry.agent}
              <span className="trace__blurb">{AGENT_BLURB[entry.agent]}</span>
            </p>
            <p className="trace__label">{entry.status === 'done' ? entry.detail ?? entry.label : entry.label}</p>
          </div>
        </li>
      ))}
    </ol>
  )
}
