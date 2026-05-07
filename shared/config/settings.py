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

    mbh_account_base_url: str = os.getenv("MBH_ACCOUNT_BASE_URL", "")
    mbh_account_client_id: str = os.getenv("MBH_ACCOUNT_CLIENT_ID", "")

    mbh_payment_base_url: str = os.getenv("MBH_PAYMENT_BASE_URL", "")
    mbh_payment_client_id: str = os.getenv("MBH_PAYMENT_CLIENT_ID", "")

    mbh_redirect_uri: str = os.getenv("MBH_REDIRECT_URI", "")
    mbh_issuer_url: str = os.getenv("MBH_ISSUER_URL", "")
    mbh_private_key_path: str = os.getenv("MBH_PRIVATE_KEY_PATH", "")
    mbh_public_key_path: str = os.getenv("MBH_PUBLIC_KEY_PATH", "")
    mbh_token_url: str = os.getenv("MBH_TOKEN_URL", "")
    mbh_authorization_url: str = os.getenv("MBH_AUTHORIZATION_URL", "")
    mbh_account_info_base_path: str = os.getenv("MBH_ACCOUNT_INFO_BASE_PATH", "")
    mbh_signing_iss: str = os.getenv("MBH_SIGNING_ISS", "")
    mbh_environment: str = os.getenv("MBH_ENVIRONMENT", "sandbox")

    mbh_qwac_cert_path: str = os.getenv("MBH_QWAC_CERT_PATH", "")
    mbh_qwac_key_path: str = os.getenv("MBH_QWAC_KEY_PATH", "")

    mbh_qseal_cert_path: str = os.getenv("MBH_QSEAL_CERT_PATH", "")
    mbh_qseal_key_path: str = os.getenv("MBH_QSEAL_KEY_PATH", "")

    mbh_signing_issuer: str = os.getenv(
        "MBH_SIGNING_ISSUER",
        "C=HU, ST=Hungary, L=Dunakeszi, O=NF Office Kft.",
    )

settings = Settings()
