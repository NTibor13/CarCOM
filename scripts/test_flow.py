import argparse
import json

from shared.database.schema import init_database
from services.flow_service.flow_executor import FlowExecutor


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manually run SALE flow for a transaction."
    )
    parser.add_argument(
        "transaction_id",
        type=int,
        help="finance_transactions.id value",
    )

    args = parser.parse_args()

    init_database()

    result = FlowExecutor().run_sale_flow(
        transaction_id=args.transaction_id,
    )

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()