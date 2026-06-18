"""
Liest Konfiguration aus Umgebungsvariablen (optional über eine .env-Datei,
falls python-dotenv installiert ist). Hält Secrets (Kicktipp-Login,
DB-Connection-String) aus dem Code heraus.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # python-dotenv ist optional; Variablen können auch direkt gesetzt werden.

from kicktipp_analytics.extraction.auth import KicktippCredentials


@dataclass(frozen=True, slots=True)
class Settings:
    kicktipp_credentials: KicktippCredentials
    season: str
    sql_connection_url: str | None
    csv_output_dir: str | None
    headless_browser: bool

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            kicktipp_credentials=KicktippCredentials(
                username=os.environ["KICKTIPP_USERNAME"],
                password=os.environ["KICKTIPP_PASSWORD"],
                community_url=os.environ["KICKTIPP_COMMUNITY_URL"],
            ),
            season=os.environ.get("SEASON", "wm2026"),
            sql_connection_url=os.environ.get("SQL_CONNECTION_URL"),
            csv_output_dir=os.environ.get("CSV_OUTPUT_DIR"),
            headless_browser=os.environ.get("HEADLESS_BROWSER", "true").lower() == "true",
        )
