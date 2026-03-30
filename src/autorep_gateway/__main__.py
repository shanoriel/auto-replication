from __future__ import annotations

import uvicorn

from .config import settings
from .main import app_file


def main() -> int:
    uvicorn.run(app_file(), host=settings.host, port=settings.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
