from shared.logging.logger import get_logger
from services.sync_service.google_sheets_client import GoogleSheetsClient
from services.sync_service.hashing import create_hash
from services.sync_service.sheet_mapper import rows_to_dicts
from services.sync_service.sync_repository import SyncRepository

logger = get_logger(__name__)


class SyncService:
    def __init__(self) -> None:
        self.client = GoogleSheetsClient()
        self.repository = SyncRepository()

    def run_once(self) -> dict[str, int]:
        sync_run_id = self.repository.create_sync_run()
        logger.info("Sync started. sync_run_id=%s", sync_run_id)

        try:
            values = self.client.read_values()
            rows = rows_to_dicts(values)
            counters = self.repository.sync_rows(sync_run_id, rows, create_hash)

            self.repository.finish_sync_run(
                sync_run_id=sync_run_id,
                status="success",
                rows_read=len(rows),
                inserted_count=counters["inserted"],
                updated_count=counters["updated"],
                deleted_count=counters["deleted"],
            )

            logger.info(
                "Sync finished. rows=%s inserted=%s updated=%s deleted=%s",
                len(rows),
                counters["inserted"],
                counters["updated"],
                counters["deleted"],
            )
            return {"rows_read": len(rows), **counters}

        except Exception as exc:
            self.repository.finish_sync_run(sync_run_id=sync_run_id, status="failed", error_message=str(exc))
            logger.exception("Sync failed. sync_run_id=%s", sync_run_id)
            raise
