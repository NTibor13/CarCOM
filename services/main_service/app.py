import argparse


from shared.config.settings import settings
from shared.database.schema import init_database
from shared.logging.logger import get_logger
from services.main_service.processing_repository import ProcessingRepository
from services.main_service.finance_normalizer import FinanceNormalizer

logger = get_logger(__name__)


def run_sync_once() -> None:
    from services.sync_service.service import SyncService

    init_database()
    result = SyncService().run_once()
    logger.info("Sync result: %s", result)


def normalize_finance() -> None:
    init_database()

    result = FinanceNormalizer().normalize_active_rows()
    logger.info("Finance normalization result: %s", result)


def run_pipeline_once() -> None:
    from services.sync_service.service import SyncService

    init_database()
    sync_result = SyncService().run_once()
    processing_result = ProcessingRepository().ensure_processing_items_for_active_rows()
    normalization_result = FinanceNormalizer().normalize_active_rows()

    logger.info("Pipeline sync result: %s", sync_result)
    logger.info("Pipeline processing result: %s", processing_result)
    logger.info("Pipeline finance normalization result: %s", normalization_result)


def prepare_processing() -> None:
    init_database()

    repository = ProcessingRepository()
    result = repository.ensure_processing_items_for_active_rows()
    summary = repository.get_status_summary()

    logger.info("Processing prepare result: %s", result)
    logger.info("Processing status summary: %s", summary)


def run_scheduler() -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler

    init_database()

    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_pipeline_once,
        "interval",
        seconds=settings.sync_interval_seconds,
        id="google_sheet_finance_sync",
        max_instances=1,
        coalesce=True,
    )

    logger.info("CarCOM scheduler started. interval_seconds=%s", settings.sync_interval_seconds)
    run_pipeline_once()
    scheduler.start()


def main() -> None:
    parser = argparse.ArgumentParser(prog="CarCOM main service")
    parser.add_argument("--once", action="store_true", help="Run sync once and exit")
    parser.add_argument("--scheduler", action="store_true", help="Run sync periodically")
    parser.add_argument("--prepare-processing", action="store_true", help="Create processing items for active Sheet rows")
    parser.add_argument("--normalize-finance", action="store_true", help="Normalize raw Sheet rows into finance transactions")
    parser.add_argument("--pipeline", action="store_true", help="Run sync, processing preparation and finance normalization")

    args = parser.parse_args()

    if args.prepare_processing:
        prepare_processing()
        return

    if args.normalize_finance:
        normalize_finance()
        return

    if args.pipeline:
        run_pipeline_once()
        return

    if args.scheduler:
        run_scheduler()
        return

    run_sync_once()


if __name__ == "__main__":
    main()