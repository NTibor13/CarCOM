import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from shared.google_auth_errors import GoogleAuthenticationRequiredError
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from shared.config.settings import settings

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


class GoogleSheetsClient:
    def __init__(self) -> None:
        self.credentials = self._load_oauth_credentials()
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

    def read_document_links(self, document_columns: list[str]) -> dict[tuple[int, str], list[dict[str, str]]]:
        range_name = f"'{settings.google_worksheet_name}'!{settings.google_range}"

        result = (
            self.service.spreadsheets()
            .get(
                spreadsheetId=settings.google_sheet_id,
                ranges=[range_name],
                includeGridData=True,
                fields=(
                    "sheets("
                    "properties(title),"
                    "data("
                    "startRow,"
                    "startColumn,"
                    "rowData("
                    "values("
                    "formattedValue,"
                    "hyperlink,"
                    "textFormatRuns(startIndex,format(link(uri))),"
                    "chipRuns(startIndex,chip(richLinkProperties(uri)))"
                    ")"
                    ")"
                    ")"
                    ")"
                ),
            )
            .execute()
        )

        target_sheet = None
        for sheet in result.get("sheets", []):
            if sheet.get("properties", {}).get("title") == settings.google_worksheet_name:
                target_sheet = sheet
                break

        if not target_sheet:
            return {}

        data_blocks = target_sheet.get("data", [])
        if not data_blocks:
            return {}

        row_data = data_blocks[0].get("rowData", [])
        if not row_data:
            return {}

        header_cells = row_data[0].get("values", [])
        headers = [
            str(cell.get("formattedValue", "")).strip()
            for cell in header_cells
        ]

        document_column_indexes = {
            index: header
            for index, header in enumerate(headers)
            if header in document_columns
        }

        documents_by_cell: dict[tuple[int, str], list[dict[str, str]]] = {}

        for row_index, row in enumerate(row_data[1:], start=2):
            values = row.get("values", [])

            for col_index, source_column in document_column_indexes.items():
                if col_index >= len(values):
                    continue

                cell = values[col_index]
                links = self._extract_links_from_cell(cell)

                if links:
                    documents_by_cell[(row_index, source_column)] = links

        return documents_by_cell

    def _extract_links_from_cell(self, cell: dict) -> list[dict[str, str]]:
        links: list[dict[str, str]] = []
        formatted_value = str(cell.get("formattedValue", "")).strip()

        if cell.get("hyperlink"):
            links.append({
                "file_name": formatted_value or cell["hyperlink"],
                "file_url": cell["hyperlink"],
                "raw_value": formatted_value,
            })

        text_runs = cell.get("textFormatRuns", [])

        for index, run in enumerate(text_runs):
            uri = (
                run.get("format", {})
                .get("link", {})
                .get("uri")
            )

            if not uri:
                continue

            start_index = run.get("startIndex", 0)

            if index + 1 < len(text_runs):
                end_index = text_runs[index + 1].get("startIndex", len(formatted_value))
            else:
                end_index = len(formatted_value)

            file_name = formatted_value[start_index:end_index].strip()

            links.append({
                "file_name": file_name or formatted_value or uri,
                "file_url": uri,
                "raw_value": formatted_value,
            })

        chip_runs = cell.get("chipRuns", [])

        for index, chip_run in enumerate(chip_runs):
            rich_link = (
                chip_run.get("chip", {})
                .get("richLinkProperties", {})
            )

            uri = rich_link.get("uri")

            if not uri:
                continue

            start_index = chip_run.get("startIndex", 0)

            if index + 1 < len(chip_runs):
                end_index = chip_runs[index + 1].get("startIndex", len(formatted_value))
            else:
                end_index = len(formatted_value)

            file_name = formatted_value[start_index:end_index].strip()

            links.append({
                "file_name": file_name or formatted_value or uri,
                "file_url": uri,
                "raw_value": formatted_value,
            })

        unique_links = []
        seen = set()

        for link in links:
            key = (link.get("file_url"), link.get("file_name"))
            if key not in seen:
                unique_links.append(link)
                seen.add(key)

        return unique_links

    def update_row_values(self, row_number: int, values_by_header: dict[str, str]) -> None:
        header_range = f"'{settings.google_worksheet_name}'!1:1"

        header_result = (
            self.service.spreadsheets()
            .values()
            .get(
                spreadsheetId=settings.google_sheet_id,
                range=header_range,
            )
            .execute()
        )

        headers = [h.strip() for h in header_result.get("values", [[]])[0]]

        updates = []

        for header_name, value in values_by_header.items():
            header_name = header_name.strip()
            if header_name not in headers:
                raise ValueError(f"Google Sheet column not found: {header_name}")

            col_index = headers.index(header_name)
            col_letter = self._column_index_to_letter(col_index + 1)

            updates.append({
                "range": f"'{settings.google_worksheet_name}'!{col_letter}{row_number}",
                "values": [[value]],
            })

        if not updates:
            return

        (
            self.service.spreadsheets()
            .values()
            .batchUpdate(
                spreadsheetId=settings.google_sheet_id,
                body={
                    "valueInputOption": "USER_ENTERED",
                    "data": updates,
                },
            )
            .execute()
        )

    def _column_index_to_letter(self, index: int) -> str:
        letters = ""

        while index:
            index, remainder = divmod(index - 1, 26)
            letters = chr(65 + remainder) + letters

        return letters

    def update_drive_file_chip(
            self,
            row_number: int,
            header_name: str,
            file_id: str,
    ) -> None:
        sheet_id = self._get_sheet_id()
        column_index = self._get_column_index_by_header(header_name)

        self.service.spreadsheets().batchUpdate(
            spreadsheetId=settings.google_sheet_id,
            body={
                "requests": [
                    {
                        "updateCells": {
                            "range": {
                                "sheetId": sheet_id,
                                "startRowIndex": row_number - 1,
                                "endRowIndex": row_number,
                                "startColumnIndex": column_index,
                                "endColumnIndex": column_index + 1,
                            },
                            "rows": [
                                {
                                    "values": [
                                        {
                                            "userEnteredValue": {
                                                "stringValue": "@"
                                            },
                                            "chipRuns": [
                                                {
                                                    "startIndex": 0,
                                                    "chip": {
                                                        "richLinkProperties": {
                                                            "uri": f"https://drive.google.com/file/d/{file_id}/view"
                                                        }
                                                    },
                                                }
                                            ],
                                        }
                                    ]
                                }
                            ],
                            "fields": "userEnteredValue,chipRuns",
                        }
                    }
                ]
            },
        ).execute()

    def _get_sheet_id(self) -> int:
        spreadsheet = (
            self.service.spreadsheets()
            .get(
                spreadsheetId=settings.google_sheet_id,
                fields="sheets.properties",
            )
            .execute()
        )

        for sheet in spreadsheet["sheets"]:
            properties = sheet["properties"]
            if properties["title"] == settings.google_worksheet_name:
                return properties["sheetId"]

        raise ValueError(f"Google worksheet not found: {settings.google_worksheet_name}")

    def _get_column_index_by_header(self, header_name: str) -> int:
        header_range = f"'{settings.google_worksheet_name}'!1:1"

        header_result = (
            self.service.spreadsheets()
            .values()
            .get(
                spreadsheetId=settings.google_sheet_id,
                range=header_range,
            )
            .execute()
        )

        headers = [
            str(h).strip()
            for h in header_result.get("values", [[]])[0]
        ]

        normalized_header_name = header_name.strip()

        if normalized_header_name not in headers:
            raise ValueError(f"Google Sheet column not found: {header_name}")

        return headers.index(normalized_header_name)

    def _load_oauth_credentials(self) -> Credentials:
        credentials = None
        token_file = settings.google_oauth_token_file
        client_file = settings.google_oauth_client_file

        if os.path.exists(token_file):
            try:
                credentials = Credentials.from_authorized_user_file(
                    token_file,
                    SCOPES,
                )
            except Exception as exc:
                raise GoogleAuthenticationRequiredError(
                    "Google OAuth token nem olvasható vagy sérült. "
                    "Újraautentikálás szükséges."
                ) from exc

        if credentials and credentials.valid:
            return credentials

        if credentials and credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
                self._save_credentials(credentials)
                return credentials
            except Exception as exc:
                raise GoogleAuthenticationRequiredError(
                    "Google OAuth token lejárt, és nem sikerült automatikusan frissíteni. "
                    "Újraautentikálás szükséges."
                ) from exc

        if credentials:
            raise GoogleAuthenticationRequiredError(
                "Google OAuth token érvénytelen vagy nincs refresh_token. "
                "Újraautentikálás szükséges."
            )

        if not os.path.exists(client_file):
            raise GoogleAuthenticationRequiredError(
                f"Google OAuth client file nem található: {client_file}"
            )

        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                client_file,
                SCOPES,
            )
            credentials = flow.run_local_server(
                port=0,
                prompt="consent",
            )
            self._save_credentials(credentials)
            return credentials
        except Exception as exc:
            raise GoogleAuthenticationRequiredError(
                "Google OAuth bejelentkezés nem sikerült. "
                "Újraautentikálás szükséges."
            ) from exc

    def _save_credentials(self, credentials: Credentials) -> None:
        token_file = settings.google_oauth_token_file
        token_dir = os.path.dirname(token_file)

        if token_dir:
            os.makedirs(token_dir, exist_ok=True)

        with open(token_file, "w", encoding="utf-8") as token:
            token.write(credentials.to_json())