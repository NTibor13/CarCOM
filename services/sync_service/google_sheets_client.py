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
