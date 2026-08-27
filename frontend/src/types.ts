export type Requirement = { text: string; kind: 'must_have' | 'nice_to_have' }

export type JobBrief = {
  company: string
  role: string
  seniority: string
  requirements: Requirement[]
  keywords: string[]
  company_signals: string[]
}

export type RequirementMatch = { requirement: string; evidence: string; score: number }

export type MatchReport = {
  overall_fit: number
  matches: RequirementMatch[]
  strengths: string[]
  gaps: string[]
  quick_wins: string[]
}

export type Application = { headline: string; cv_bullets: string[]; cover_letter: string }

export type Critique = { score: number; approved: boolean; issues: string[]; instructions: string }

export type InterviewQuestion = { question: string; why_asked: string; star_answer: string }

export type InterviewPack = { questions: InterviewQuestion[]; questions_to_ask_them: string[] }

export type RunResult = {
  run_id: string
  brief: JobBrief
  match: MatchReport
  application: Application
  critique: Critique
  interview: InterviewPack
  revisions: number
}

export type AgentName = 'scout' | 'matcher' | 'writer' | 'critic' | 'interviewer'

export type RunEvent = {
  type: 'run_started' | 'agent_started' | 'agent_finished' | 'run_finished' | 'error' | 'quota'
  agent: string
  message: string
  data: Record<string, unknown> | null
}

export type TraceEntry = {
  agent: AgentName
  label: string
  status: 'running' | 'done'
  detail?: string
}
