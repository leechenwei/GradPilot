import io

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app import ingest
from app.main import app

CV_TEXT = (
    "Chen Wei, CS graduate. Built a Python REST API for a campus club with 40 users. "
    "Coursework in SQL and machine learning."
)


def blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_text_upload_is_cleaned():
    text = ingest.text_from_upload("cv.txt", (CV_TEXT + "\n\n\n\n  spaced   out").encode())
    assert "spaced out" in text
    assert "\n\n\n" not in text


def test_unsupported_extension_is_refused():
    with pytest.raises(ingest.IngestError, match="PDF"):
        ingest.text_from_upload("cv.docx", b"x" * 100)


def test_oversized_upload_is_refused():
    with pytest.raises(ingest.IngestError, match="5 MB"):
        ingest.text_from_upload("cv.pdf", b"x" * (ingest.MAX_UPLOAD_BYTES + 1))


def test_image_only_pdf_tells_the_user_why():
    """A scanned CV has pages but no text layer. Say so instead of returning ''."""
    with pytest.raises(ingest.IngestError, match="scan"):
        ingest.text_from_upload("scan.pdf", blank_pdf())


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://127.0.0.1:8000/api/health",
        "http://localhost/",
        "file:///etc/passwd",
        "http://[::1]/",
    ],
)
def test_ssrf_targets_are_refused(url):
    with pytest.raises(ingest.IngestError):
        ingest.fetch_posting(url)


def test_walled_boards_fail_fast_with_advice():
    with pytest.raises(ingest.IngestError, match="paste"):
        ingest.fetch_posting("https://www.linkedin.com/jobs/view/123456")


def test_html_is_reduced_to_visible_text():
    html = (
        "<html><head><style>.a{color:red}</style></head><body>"
        "<script>alert(1)</script><h1>Data Engineer</h1>"
        "<p>We need Python &amp; SQL.</p></body></html>"
    )
    text = ingest._html_text(html)
    assert "Data Engineer" in text
    assert "We need Python & SQL." in text
    assert "alert" not in text and "color:red" not in text


def test_extract_endpoint_returns_text():
    client = TestClient(app)
    response = client.post(
        "/api/extract", files={"file": ("cv.txt", CV_TEXT.encode(), "text/plain")}
    )
    assert response.status_code == 200
    assert response.json()["chars"] == len(CV_TEXT)


def test_extract_endpoint_rejects_bad_file_with_a_readable_message():
    client = TestClient(app)
    response = client.post(
        "/api/extract", files={"file": ("cv.docx", b"x" * 50, "application/msword")}
    )
    assert response.status_code == 400
    assert "paste" in response.json()["detail"].lower()


def test_import_endpoint_refuses_private_targets():
    client = TestClient(app)
    response = client.post("/api/import", json={"url": "http://127.0.0.1:8000/"})
    assert response.status_code == 400


class _FakeSocket:
    def __init__(self, peer: str) -> None:
        self._peer = peer

    def getpeername(self) -> tuple[str, int]:
        return (self._peer, 443)


class _FakeStream:
    def __init__(self, peer: str) -> None:
        self._sock = _FakeSocket(peer)

    def get_extra_info(self, _name: str) -> _FakeSocket:
        return self._sock


def _response_from(peer: str):
    import httpx

    return httpx.Response(200, extensions={"network_stream": _FakeStream(peer)})


def test_peer_check_blocks_a_rebound_private_address():
    """DNS said public at pre-flight; the socket actually landed inside. Refuse."""
    with pytest.raises(ingest.IngestError, match="private network"):
        ingest._guard_peer(_response_from("169.254.169.254"))


def test_peer_check_allows_a_public_address():
    ingest._guard_peer(_response_from("93.184.216.34"))


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://boards.greenhouse.io/discord/jobs/7616993",
            ("greenhouse", "https://boards-api.greenhouse.io/v1/boards/discord/jobs/7616993"),
        ),
        (
            "https://job-boards.greenhouse.io/vercel/jobs/6136160004?gh_src=x",
            ("greenhouse", "https://boards-api.greenhouse.io/v1/boards/vercel/jobs/6136160004"),
        ),
        (
            "https://jobs.lever.co/acme/aa2b0a3f-79b7-4a6a-9d6d-9b1234567890",
            ("lever", "https://api.lever.co/v0/postings/acme/aa2b0a3f-79b7-4a6a-9d6d-9b1234567890"),
        ),
        ("https://company.com/careers/data-engineer", None),
    ],
)
def test_ats_urls_map_to_their_public_api(url, expected):
    assert ingest._ats_api(url) == expected


def test_ats_html_arrives_entity_escaped_and_must_be_unescaped():
    """Greenhouse ships the description escaped inside JSON: &lt;p&gt;, not <p>."""
    text = ingest._html_text("&lt;p&gt;We need &lt;b&gt;Python&lt;/b&gt; and SQL.&lt;/p&gt;")
    assert "We need Python and SQL." in text
    assert "<p>" not in text and "&lt;" not in text
