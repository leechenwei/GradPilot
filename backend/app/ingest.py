"""Turn a PDF upload or a job-ad URL into plain text.

Both paths are trust boundaries: the file is attacker-supplied, and the URL makes
this server issue a request on a stranger's behalf. Guard both, then hand the
agents the same plain text a paste would have produced.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGES = 20
MAX_FETCH_BYTES = 2 * 1024 * 1024
FETCH_TIMEOUT = 15.0
# A job ad served to a bot is usually a login wall. Say who we are anyway.
USER_AGENT = "GradPilotBot/0.1 (+https://github.com/leechenwei/GradPilot)"

# Boards that hard-block server-side fetches. Fail fast with advice, not a timeout.
WALLED = ("linkedin.com", "indeed.com", "glassdoor.com", "jobstreet.com", "seek.com")


class IngestError(ValueError):
    """Bad input from the user — always safe to show them the message."""


def text_from_upload(name: str, blob: bytes) -> str:
    if len(blob) > MAX_UPLOAD_BYTES:
        raise IngestError("That file is over 5 MB. Export a smaller PDF or paste the text.")
    lower = name.lower()
    if lower.endswith(".pdf"):
        return _clean(_pdf_text(blob))
    if lower.endswith((".txt", ".md")):
        return _clean(blob.decode("utf-8", "replace"))
    raise IngestError("Upload a PDF, .txt or .md file, or paste the text instead.")


def _pdf_text(blob: bytes) -> str:
    from io import BytesIO

    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(BytesIO(blob))
        pages = reader.pages[:MAX_PDF_PAGES]
        text = "\n".join(page.extract_text() or "" for page in pages)
    except (PdfReadError, OSError, ValueError) as exc:
        raise IngestError("That PDF could not be read. Try 'Save as PDF' again, or paste.") from exc
    if len(text.strip()) < 40:
        raise IngestError(
            "No text found — the PDF is probably a scan or an image export. "
            "Paste the text, or re-export it from Word or Docs."
        )
    return text


def fetch_posting(url: str) -> str:
    """GET a job ad and return its visible text. Refuses anything not public HTTP."""
    _guard_url(url)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,*/*"}
    try:
        with httpx.Client(timeout=FETCH_TIMEOUT, follow_redirects=False) as client:
            # Streamed so the socket can be checked before a single byte of body is read:
            # the pre-flight DNS answer and the one httpx connects with are two lookups,
            # and a rebinding host can answer public then private between them.
            with client.stream("GET", url, headers=headers) as response:
                _guard_peer(response)
                if response.status_code in (301, 302, 303, 307, 308):
                    raise IngestError(
                        "That link redirects. Open it, copy the final URL, and try that."
                    )
                if response.status_code >= 400:
                    raise IngestError(
                        f"The site answered {response.status_code}. Most job boards block "
                        "bots — paste the posting text instead."
                    )
                blob = b""
                for chunk in response.iter_bytes():
                    blob += chunk
                    if len(blob) >= MAX_FETCH_BYTES:
                        break
                encoding = response.encoding or "utf-8"
    except httpx.HTTPError as exc:
        raise IngestError("That page could not be reached. Paste the posting instead.") from exc

    text = _clean(_html_text(blob[:MAX_FETCH_BYTES].decode(encoding, "replace")))
    if len(text) < 200:
        raise IngestError(
            "That page loaded but held almost no text, so it is rendered by JavaScript "
            "or behind a login. Paste the posting instead."
        )
    return text


def _check_ip(raw: str) -> None:
    """One rule for both the pre-flight lookup and the socket actually connected."""
    address = ipaddress.ip_address(raw)
    # SSRF: without this, a link resolving to 169.254.169.254 reads cloud metadata.
    if not address.is_global or address.is_loopback or address.is_private:
        raise IngestError("That link points inside a private network.")


def _guard_peer(response: httpx.Response) -> None:
    """Re-check the peer of the open socket, which defeats a DNS rebinding swap.

    # ponytail: this blocks reading an internal response, not the bare connect. A
    # blind request can still reach the peer. Pin the validated IP with a custom
    # transport if a blind hit ever matters here.
    """
    stream = response.extensions.get("network_stream")
    sock = stream.get_extra_info("socket") if stream is not None else None
    peer = sock.getpeername() if sock is not None else None
    if peer:
        _check_ip(str(peer[0]))


def _guard_url(url: str) -> None:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise IngestError("Give a full http(s) link.")
    host = parsed.hostname
    if any(host == w or host.endswith("." + w) for w in WALLED):
        raise IngestError(
            f"{host} blocks automated fetches — it needs a login. "
            "Open the ad, select all, and paste it here instead."
        )
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise IngestError("That host does not resolve.") from exc
    for info in infos:
        _check_ip(str(info[4][0]))


class _Stripper(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head"}
    BREAK = {"p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "section"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skipping = 0

    def handle_starttag(self, tag: str, attrs: object) -> None:
        if tag in self.SKIP:
            self._skipping += 1
        elif tag in self.BREAK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skipping:
            self._skipping -= 1

    def handle_data(self, data: str) -> None:
        if not self._skipping and data.strip():
            self.parts.append(data.strip())


def _html_text(html: str) -> str:
    stripper = _Stripper()
    stripper.feed(html)
    return " ".join(stripper.parts)


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace(" ", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()[:20_000]
