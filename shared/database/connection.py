import os
import sqlite3
from shared.config.settings import settings


def get_connection() -> sqlite3.Connection:
    db_dir = os.path.dirname(settings.database_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    return conn
