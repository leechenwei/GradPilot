export type RunEvent =
  | { type: "start"; agent: string; revision: number }
  | { type: "result"; agent: string; revision: number; data: Record<string, unknown> }
  | { type: "done"; result: Record<string, unknown> }
  | { type: "error"; message: string };

// `||`, not `??`: an env var that reaches the build as "" would otherwise make every
// call same-origin and 404 on the host serving the page.
const BASE = import.meta.env.VITE_API_BASE?.trim().replace(/\/+$/, "") || "http://localhost:8000";

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

async function post(path: string, init: RequestInit): Promise<{ text: string }> {
  const response = await fetch(`${BASE}${path}`, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail ?? `Request failed (${response.status})`);
  return body;
}

/** PDF or text file in, plain text back. The file never leaves memory server-side. */
export async function extractFile(file: File): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  return (await post("/api/extract", { method: "POST", body: form })).text;
}

export async function importPosting(url: string): Promise<string> {
  return (
    await post("/api/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    })
  ).text;
}
