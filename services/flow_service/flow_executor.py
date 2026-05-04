from services.flow_service.flow_repository import FlowRepository
from services.flow_service.flow_steps import SALE_FLOW_STEPS, STEP_HANDLERS


class FlowExecutor:
    def __init__(self, repository: FlowRepository | None = None):
        self.repository = repository or FlowRepository()

    def run_sale_flow(self, transaction_id: int, force_new_run: bool = False) -> dict:
        if force_new_run:
            flow_run = self.repository.create_flow_run(
                transaction_id=transaction_id,
                flow_type="SALE",
            )
        else:
            flow_run = self.repository.get_or_create_flow_run(
                transaction_id=transaction_id,
                flow_type="SALE",
            )

        flow_run_id = flow_run["id"]
        self.repository.mark_flow_running(flow_run_id)

        executed_steps = []
        skipped_steps = []

        try:
            for step in SALE_FLOW_STEPS:
                step_name = step["name"]
                step_order = step["order"]

                existing_step_log = self.repository.get_step_log(
                    flow_run_id=flow_run_id,
                    step_name=step_name,
                )

                if existing_step_log and existing_step_log["status"] == "SUCCESS":
                    skipped_steps.append(step_name)
                    continue

                handler = STEP_HANDLERS.get(step_name)

                if handler is None:
                    raise RuntimeError(f"No handler registered for step: {step_name}")

                context = {
                    "transaction_id": transaction_id,
                    "flow_type": "SALE",
                    "flow_run_id": flow_run_id,
                    "step_name": step_name,
                }

                self.repository.start_step(
                    flow_run_id=flow_run_id,
                    step_name=step_name,
                    step_order=step_order,
                    input_data=context,
                )

                result = handler(context)

                if result.get("status") == "skipped":
                    self.repository.mark_step_skipped(
                        flow_run_id=flow_run_id,
                        step_name=step_name,
                        output_data=result,
                    )

                    self.repository.mark_flow_skipped(
                        flow_run_id=flow_run_id,
                        reason=result.get("reason"),
                    )

                    executed_steps.append(step_name)

                    return {
                        "flow_run_id": flow_run_id,
                        "status": "SKIPPED",
                        "reason": result.get("reason"),
                        "executed_steps": executed_steps,
                        "skipped_steps": skipped_steps,
                    }

                self.repository.mark_step_success(
                    flow_run_id=flow_run_id,
                    step_name=step_name,
                    output_data=result,
                )

                executed_steps.append(step_name)

            self.repository.mark_flow_success(flow_run_id)

            return {
                "flow_run_id": flow_run_id,
                "status": "SUCCESS",
                "executed_steps": executed_steps,
                "skipped_steps": skipped_steps,
            }

        except Exception as exc:
            error_message = str(exc)

            if "step_name" in locals():
                self.repository.mark_step_failed(
                    flow_run_id=flow_run_id,
                    step_name=step_name,
                    error_message=error_message,
                )

            self.repository.mark_flow_failed(
                flow_run_id=flow_run_id,
                error_message=error_message,
            )

            return {
                "flow_run_id": flow_run_id,
                "status": "FAILED",
                "error_message": error_message,
                "executed_steps": executed_steps,
                "skipped_steps": skipped_steps,
            }