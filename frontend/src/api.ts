import type { RunEvent } from './types'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

const CLIENT_ID_KEY = 'gradpilot:client-id'

function clientId(): string {
  let id = localStorage.getItem(CLIENT_ID_KEY)
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem(CLIENT_ID_KEY, id)
  }
  return id
}

export type RunInput = { job_posting: string; cv: string; target_role: string }

export async function fetchSample(): Promise<RunInput> {
  const response = await fetch(`${API_BASE}/api/sample`)
  if (!response.ok) throw new Error('Could not load the sample')
  return response.json()
}

/**
 * POSTs the run and yields each SSE frame as it arrives. `fetch` is used rather
 * than EventSource because the run needs a request body.
 */
export async function* streamRun(input: RunInput, signal: AbortSignal): AsyncGenerator<RunEvent> {
  const response = await fetch(`${API_BASE}/api/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Client-Id': clientId() },
    body: JSON.stringify(input),
    signal,
  })

  if (response.status === 429) {
    const body = await response.json()
    throw new Error(
      `You have used all ${body.detail?.limit ?? ''} free runs for today. Come back tomorrow or upgrade.`,
    )
  }
  if (!response.ok || !response.body) {
    throw new Error(`The server rejected the request (${response.status}).`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''
    for (const frame of frames) {
      const line = frame.split('\n').find((candidate) => candidate.startsWith('data: '))
      if (line) yield JSON.parse(line.slice(6)) as RunEvent
    }
  }
}
