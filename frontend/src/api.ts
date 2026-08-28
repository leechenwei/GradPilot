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

export type Wallet = {
  remaining: number;
  free_runs: number;
  credits: number;
  package: { runs: number; price: string };
  can_buy: boolean;
  model_ready: boolean;
};

/** The key lives in this browser only. It is sent per request and never persisted server-side. */
export function readKey(): { provider: string; key: string } {
  return {
    provider: localStorage.getItem("gradpilot.provider") ?? "openai",
    key: localStorage.getItem("gradpilot.key") ?? "",
  };
}

export function saveKey(provider: string, key: string): void {
  localStorage.setItem("gradpilot.provider", provider);
  if (key) localStorage.setItem("gradpilot.key", key);
  else localStorage.removeItem("gradpilot.key");
}

function headers(): Record<string, string> {
  const { provider, key } = readKey();
  return key
    ? { "X-Session-Id": sessionId(), "X-LLM-Provider": provider, "X-LLM-Key": key }
    : { "X-Session-Id": sessionId() };
}

export async function wallet(): Promise<Wallet> {
  const response = await fetch(`${BASE}/api/quota`, {
    headers: { "X-Session-Id": sessionId() },
  });
  return await response.json();
}

export async function startCheckout(): Promise<string> {
  const response = await fetch(`${BASE}/api/checkout`, {
    method: "POST",
    headers: { "X-Session-Id": sessionId() },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail ?? "Checkout is unavailable.");
  return body.url;
}

/** POST + SSE. EventSource cannot POST, so the stream is parsed by hand. */
export async function* streamRun(posting: string, cv: string): AsyncGenerator<RunEvent> {
  const response = await fetch(`${BASE}/api/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers() },
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
