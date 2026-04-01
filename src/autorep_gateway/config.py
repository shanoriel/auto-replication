from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    host: str = "0.0.0.0"
    port: int = 11451
    app_name: str = "AutoReplication Gateway"
    root_dir: Path = Path(__file__).resolve().parents[2]
    data_dir: Path = Path(__file__).resolve().parents[2] / "data"
    db_path: Path = Path(__file__).resolve().parents[2] / "data" / "gateway.db"
    static_dir: Path = Path(__file__).resolve().parents[2] / "static"
    catalog_path: Path = Path(__file__).resolve().parents[2] / "data" / "catalog.json"
    agent_asset_dir: Path = Path(__file__).resolve().parents[2] / "data" / "agent-assets"


settings = Settings()
