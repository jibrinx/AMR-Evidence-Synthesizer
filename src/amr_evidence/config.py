"""Operator-only configuration. Never expose credentials or endpoint editing to the agent."""

import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit


def flag(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.lower().strip()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise ValueError(f"{name} must be true or false; refusing ambiguous configuration.")


@dataclass(frozen=True)
class Settings:
    db_path: str = "data/evidence.sqlite3"
    read_only: bool = True
    ai_enabled: bool = False
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = ""
    ai_api_key: str = field(default="", repr=False)
    allow_local_http: bool = False
    ncbi_email: str = ""

    @classmethod
    def from_env(cls):
        return cls(
            db_path=os.getenv("AMR_DB_PATH", "data/evidence.sqlite3"),
            read_only=flag("AMR_READ_ONLY", True),
            ai_enabled=flag("AMR_AI_ENABLED"),
            ai_base_url=os.getenv("AMR_AI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            ai_model=os.getenv("AMR_AI_MODEL", ""),
            ai_api_key=os.getenv("AMR_AI_API_KEY", ""),
            allow_local_http=flag("AMR_ALLOW_LOCAL_HTTP"),
            ncbi_email=os.getenv("NCBI_EMAIL", ""),
        )

    def validate_ai(self):
        if self.read_only:
            raise PermissionError("AI execution is disabled in public read-only mode.")
        if not self.ai_enabled or not self.ai_model:
            raise ValueError("Operator must enable AI and set a tool-capable model.")
        url = urlsplit(self.ai_base_url)
        if not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError(
                "AI endpoint must be an operator-configured base URL without credentials or query."
            )
        local = url.hostname in {"localhost", "127.0.0.1", "::1", "host.docker.internal"}
        if url.scheme != "https":
            if not (url.scheme == "http" and local and self.allow_local_http):
                raise ValueError(
                    "Use HTTPS, or explicitly enable a loopback/local Docker HTTP model."
                )
        if not local and not self.ai_api_key:
            raise ValueError("A cloud provider API key is required in server-side configuration.")

    def public_destination(self):
        parsed = urlsplit(self.ai_base_url)
        # Deliberately omit any malformed operator-supplied credentials/query string.
        return f"{parsed.scheme}://{parsed.hostname or '(invalid host)'}{':' + str(parsed.port) if parsed.port else ''}{parsed.path}"
