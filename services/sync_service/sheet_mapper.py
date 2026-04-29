from typing import Any


def rows_to_dicts(values: list[list[str]]) -> list[dict[str, Any]]:
    if not values:
        return []

    headers = [header.strip() for header in values[0]]
    mapped_rows: list[dict[str, Any]] = []

    for row_index, row in enumerate(values[1:], start=2):
        data: dict[str, str] = {}

        for col_index, header in enumerate(headers):
            if not header:
                continue
            data[header] = row[col_index].strip() if col_index < len(row) else ""

        if any(value != "" for value in data.values()):
            mapped_rows.append({"source_row_number": row_index, "data": data})

    return mapped_rows
