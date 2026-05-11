import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from shared.google_oauth import load_oauth_credentials
from shared.config.settings import settings


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
        file_id = self._normalize_drive_file_id(file_id)
        drive_file_url = f"https://drive.google.com/file/d/{file_id}/view"
        sheet_id = self._get_sheet_id()
        column_index = self._get_column_index_by_header(header_name)

        cell_state = self._get_cell_chip_state(
            row_number=row_number,
            column_index=column_index,
        )

        existing_value = cell_state["text"]
        existing_chip_runs = cell_state["chip_runs"]

        if existing_value:
            new_value = f"{existing_value} @"
            new_chip_start_index = len(existing_value) + 1
        else:
            new_value = "@"
            new_chip_start_index = 0

        chip_runs = []

        for chip_run in existing_chip_runs:
            start_index = chip_run.get("startIndex", 0)

            uri = (
                chip_run
                .get("chip", {})
                .get("richLinkProperties", {})
                .get("uri")
            )

            if not uri:
                continue

            try:
                old_file_id = self._normalize_drive_file_id(uri)
            except Exception:
                continue

            if not old_file_id or old_file_id == "None":
                continue

            chip_runs.append(
                {
                    "startIndex": start_index,
                    "chip": {
                        "richLinkProperties": {
                            "uri": f"https://drive.google.com/file/d/{old_file_id}/view"
                        }
                    },
                }
            )

        chip_runs.append(
            {
                "startIndex": new_chip_start_index,
                "chip": {
                    "richLinkProperties": {
                        "uri": drive_file_url
                    }
                },
            }
        )

        print("DEBUG Drive chip file_id:", file_id)
        print("DEBUG Drive chip url:", drive_file_url)
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
                                                "stringValue": new_value
                                            },
                                            "chipRuns": chip_runs,
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

    def _get_cell_formatted_value(
            self,
            row_number: int,
            column_index: int,
    ) -> str:
        col_letter = self._column_index_to_letter(column_index + 1)
        cell_range = f"'{settings.google_worksheet_name}'!{col_letter}{row_number}"

        result = (
            self.service.spreadsheets()
            .values()
            .get(
                spreadsheetId=settings.google_sheet_id,
                range=cell_range,
            )
            .execute()
        )

        values = result.get("values", [])

        if not values or not values[0]:
            return ""

        return str(values[0][0]).strip()

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

    def _load_oauth_credentials(self):
        return load_oauth_credentials(interactive=False)

    def _normalize_drive_file_id(self, file_id_or_url: str) -> str:
        value = str(file_id_or_url).strip()

        if "/file/d/" in value:
            return value.split("/file/d/")[1].split("/")[0]

        if "id=" in value:
            return value.split("id=")[1].split("&")[0]

        return value

    def _get_cell_chip_state(
            self,
            row_number: int,
            column_index: int,
    ) -> dict:
        sheet_id = self._get_sheet_id()

        result = (
            self.service.spreadsheets()
            .get(
                spreadsheetId=settings.google_sheet_id,
                ranges=[],
                includeGridData=True,
            )
            .execute()
        )

        for sheet in result.get("sheets", []):
            if sheet.get("properties", {}).get("sheetId") != sheet_id:
                continue

            data = sheet.get("data", [])
            if not data:
                return {"text": "", "chip_runs": []}

        # pontosabb és gyorsabb range-alapú lekérés
        col_letter = self._column_index_to_letter(column_index + 1)
        cell_range = f"'{settings.google_worksheet_name}'!{col_letter}{row_number}"

        result = (
            self.service.spreadsheets()
            .get(
                spreadsheetId=settings.google_sheet_id,
                ranges=[cell_range],
                includeGridData=True,
            )
            .execute()
        )

        sheets = result.get("sheets", [])
        if not sheets:
            return {"text": "", "chip_runs": []}

        data = sheets[0].get("data", [])
        if not data:
            return {"text": "", "chip_runs": []}

        row_data = data[0].get("rowData", [])
        if not row_data:
            return {"text": "", "chip_runs": []}

        values = row_data[0].get("values", [])
        if not values:
            return {"text": "", "chip_runs": []}

        cell = values[0]

        text = (
                cell.get("userEnteredValue", {}).get("stringValue")
                or cell.get("formattedValue")
                or ""
        )

        chip_runs = cell.get("chipRuns", []) or []

        print("DEBUG existing cell raw:")
        print(json.dumps(cell, indent=2, ensure_ascii=False))

        print("DEBUG existing chipRuns:")
        print(json.dumps(chip_runs, indent=2, ensure_ascii=False))

        return {
            "text": text,
            "chip_runs": chip_runs,
        }

    def update_drive_file_chips(
            self,
            row_number: int,
            header_name: str,
            file_ids: list[str],
    ) -> None:
        sheet_id = self._get_sheet_id()
        column_index = self._get_column_index_by_header(header_name)

        clean_file_ids = []
        for file_id in file_ids:
            normalized = self._normalize_drive_file_id(file_id)
            if normalized and normalized != "None" and normalized not in clean_file_ids:
                clean_file_ids.append(normalized)

        if not clean_file_ids:
            raise RuntimeError("No valid Drive file IDs provided for chip update.")

        text_parts = ["@" for _ in clean_file_ids]
        new_value = "\n".join(text_parts)

        chip_runs = []
        current_index = 0

        for file_id in clean_file_ids:
            chip_runs.append(
                {
                    "startIndex": current_index,
                    "chip": {
                        "richLinkProperties": {
                            "uri": f"https://drive.google.com/file/d/{file_id}/view"
                        }
                    },
                }
            )

            current_index += 2  # "@" + "\n"

        print("DEBUG clean_file_ids:", clean_file_ids)
        print("DEBUG new_value:", repr(new_value))
        print("DEBUG chip_runs:", json.dumps(chip_runs, indent=2, ensure_ascii=False))

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
                                                "stringValue": new_value
                                            },
                                            "chipRuns": chip_runs,
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