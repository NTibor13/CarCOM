from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    env: str = os.getenv("CARCOM_ENV", "local")
    database_path: str = os.getenv("DATABASE_PATH", "data/carcom.db")

    google_sheet_id: str = os.getenv("GOOGLE_SHEET_ID", "")
    google_worksheet_name: str = os.getenv("GOOGLE_WORKSHEET_NAME", "Pénzügy")
    google_range: str = os.getenv("GOOGLE_RANGE", "A:ZZ")
    google_credentials_file: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")

    sync_interval_seconds: int = int(os.getenv("SYNC_INTERVAL_SECONDS", "300"))


settings = Settings()
