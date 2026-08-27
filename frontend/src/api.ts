export type RunEvent =
  | { type: "start"; agent: string; revision: number }
  | { type: "result"; agent: string; revision: number; data: Record<string, unknown> }
  | { type: "done"; result: Record<string, unknown> }
  | { type: "error"; message: string };

const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

/** One id per browser, so the free-run cap survives a reload. */
export function sessionId(): string {
  let id = localStorage.getItem("gradpilot.session");
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("gradpilot.session", id);
  }
  return id;
}

export async function quotaLeft(): Promise<number> {
  const response = await fetch(`${BASE}/api/quota`, {
    headers: { "X-Session-Id": sessionId() },
  });
  return (await response.json()).remaining;
}

/** POST + SSE. EventSource cannot POST, so the stream is parsed by hand. */
export async function* streamRun(posting: string, cv: string): AsyncGenerator<RunEvent> {
  const response = await fetch(`${BASE}/api/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Session-Id": sessionId() },
    body: JSON.stringify({ posting, cv }),
  });
  if (!response.ok || !response.body) {
    const detail = response.status === 429 ? "Free runs used up for this browser." : await response.text();
    yield { type: "error", message: detail };
    return;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const line = chunk.trim();
      if (line.startsWith("data: ")) yield JSON.parse(line.slice(6)) as RunEvent;
    }
  }
}
