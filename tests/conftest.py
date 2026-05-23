import os
import tempfile

import pytest

os.environ.setdefault("USE_LLM", "0")
os.environ.setdefault("DB_PATH", os.path.join(tempfile.gettempdir(), "test.db"))


@pytest.fixture(autouse=True)
def _reset_db():
    from app.core.repository import DB_PATH, init_db

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()
    yield
