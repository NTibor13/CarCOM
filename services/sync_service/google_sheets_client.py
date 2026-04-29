from google.oauth2 import service_account
from googleapiclient.discovery import build

from shared.config.settings import settings

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


class GoogleSheetsClient:
    def __init__(self) -> None:
        self.credentials = service_account.Credentials.from_service_account_file(
            settings.google_credentials_file,
            scopes=SCOPES,
        )
        self.service = build("sheets", "v4", credentials=self.credentials)

    def read_values(self) -> list[list[str]]:
        range_name = f"'{settings.google_worksheet_name}'!{settings.google_range}"
        result = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=settings.google_sheet_id, range=range_name)
            .execute()
        )
        return result.get("values", [])
