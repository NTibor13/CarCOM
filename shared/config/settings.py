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
    google_service_account_email: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", "")
    google_oauth_client_file: str = os.getenv(
        "GOOGLE_OAUTH_CLIENT_FILE",
        "credentials/google_oauth_client.json",
    )

    google_oauth_token_file: str = os.getenv(
        "GOOGLE_OAUTH_TOKEN_FILE",
        "credentials/google_oauth_token.json",
    )

    sync_interval_seconds: int = int(os.getenv("SYNC_INTERVAL_SECONDS", "300"))
    billingo_invoice_drive_folder_id: str = os.getenv("BILLINGO_INVOICE_DRIVE_FOLDER_ID", "")

settings = Settings()
