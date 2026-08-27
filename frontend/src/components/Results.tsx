import { useState } from 'react'
import type { RunResult } from '../types'
import AdSlot from './AdSlot'
import CopyButton from './CopyButton'
import FitMeter from './FitMeter'

const TABS = ['Fit', 'Application', 'Interview'] as const
type Tab = (typeof TABS)[number]

export default function Results({ result }: { result: RunResult }) {
  const [tab, setTab] = useState<Tab>('Fit')
  const { brief, match, application, critique, interview } = result

  return (
    <section className="results">
      <header className="results__header">
        <div>
          <h2>
            {brief.role} <span className="results__at">at</span> {brief.company}
          </h2>
          <p className="results__meta">
            {brief.seniority} level &middot; reviewed {result.revisions + 1}&times; by the critic &middot; final score{' '}
            {critique.score}/100
          </p>
        </div>
        <nav className="tabs" role="tablist">
          {TABS.map((name) => (
            <button
              key={name}
              role="tab"
              aria-selected={tab === name}
              className={`tabs__tab ${tab === name ? 'tabs__tab--active' : ''}`}
              onClick={() => setTab(name)}
            >
              {name}
            </button>
          ))}
        </nav>
      </header>

      {tab === 'Fit' && (
        <div className="panel">
          <div className="panel__split">
            <FitMeter value={match.overall_fit} caption="overall fit against this posting" />
            <div className="stack">
              <h3>Where you are strong</h3>
              <ul className="list list--positive">
                {match.strengths.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
              <h3>Gaps to expect questions about</h3>
              <ul className="list list--negative">
                {match.gaps.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          </div>

          <h3>Requirement by requirement</h3>
          <table className="reqs">
            <tbody>
              {match.matches.map((item) => (
                <tr key={item.requirement}>
                  <td className="reqs__score">
                    <span className={`pill pill--${item.score >= 4 ? 'good' : item.score >= 2 ? 'mid' : 'bad'}`}>
                      {item.score}/5
                    </span>
                  </td>
                  <td>
                    <strong>{item.requirement}</strong>
                    <p className="reqs__evidence">{item.evidence || 'Nothing in your CV speaks to this yet.'}</p>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3>Do these this week</h3>
          <ol className="list list--numbered">
            {match.quick_wins.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ol>
        </div>
      )}

      {tab === 'Application' && (
        <div className="panel">
          <p className="headline">{application.headline}</p>

          <div className="panel__row">
            <h3>Tailored CV bullets</h3>
            <CopyButton text={application.cv_bullets.join('\n')} label="Copy bullets" />
          </div>
          <ul className="list list--bullets">
            {application.cv_bullets.map((bullet) => (
              <li key={bullet}>{bullet}</li>
            ))}
          </ul>

          <div className="panel__row">
            <h3>Cover letter</h3>
            <CopyButton text={application.cover_letter} label="Copy letter" />
          </div>
          <pre className="letter">{application.cover_letter}</pre>

          {critique.issues.length > 0 && (
            <details className="critique">
              <summary>What the critic pushed back on</summary>
              <ul className="list list--negative">
                {critique.issues.map((issue) => (
                  <li key={issue}>{issue}</li>
                ))}
              </ul>
            </details>
          )}
          <AdSlot slot="1234567890" />
        </div>
      )}

      {tab === 'Interview' && (
        <div className="panel">
          {interview.questions.map((item) => (
            <details key={item.question} className="qa">
              <summary>{item.question}</summary>
              <p className="qa__why">{item.why_asked}</p>
              <p className="qa__answer">{item.star_answer}</p>
            </details>
          ))}
          <h3>Ask them this</h3>
          <ul className="list list--bullets">
            {interview.questions_to_ask_them.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
