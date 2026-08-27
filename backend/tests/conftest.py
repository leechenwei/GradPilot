"""Force mock mode for the whole suite.

`app.main` resolves settings at import time, so a real key in the developer's
environment would otherwise make the API tests hit a live provider.
"""

from __future__ import annotations

import os

os.environ["GRADPILOT_LLM_PROVIDER"] = "mock"
for _key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
    os.environ.pop(_key, None)
