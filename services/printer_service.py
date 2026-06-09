import logging
import time
from pathlib import Path

import cups


class PrinterError(Exception):
    pass


logger = logging.getLogger(__name__)

PRINTER_STATE_MAP = {
    3: "Ready",
    4: "Printing",
    5: "Stopped",
}

JOB_STATE_MAP = {
    3: "Pending",
    4: "Pending",
    5: "Processing",
    6: "Failed",
    7: "Failed",
    8: "Failed",
    9: "Completed",
}


class PrinterService:
    def _get_connection(self) -> cups.Connection:
        try:
            connection = cups.Connection()
            logger.info("Connected to CUPS successfully.")
            return connection
        except RuntimeError as exc:
            logger.exception("Failed to connect to CUPS.")
            raise PrinterError("Unable to connect to CUPS.") from exc

    def list_printers(self) -> list[str]:
        try:
            printers = self._get_connection().getPrinters()
            printer_names = sorted(printers.keys())
            logger.info("pycups returned %d printers: %s", len(printer_names), printer_names)
            return printer_names
        except RuntimeError as exc:
            logger.exception("CUPS printer discovery failed.")
            raise PrinterError("Unable to connect to CUPS.") from exc

    def get_printer_status(self, printer_name: str) -> dict:
        try:
            printers = self._get_connection().getPrinters()
        except RuntimeError as exc:
            logger.exception("Failed to fetch printer status for %s.", printer_name)
            raise PrinterError("Unable to connect to CUPS.") from exc

        if printer_name not in printers:
            raise PrinterError("Selected printer is unavailable.")

        printer = printers[printer_name]
        state_code = printer.get("printer-state")
        reasons = printer.get("printer-state-reasons", [])
        if isinstance(reasons, str):
            reasons = [reasons]

        normalized_state = PRINTER_STATE_MAP.get(state_code, "Offline")
        if any("offline" in reason for reason in reasons):
            normalized_state = "Offline"

        payload = {
            "printer_name": printer_name,
            "exists": True,
            "state": normalized_state,
            "state_code": state_code,
            "is_stopped": state_code == 5,
            "reasons": reasons,
        }
        logger.info("Printer status for %s: %s", printer_name, payload)
        return payload

    def get_job_status(self, job_id: int) -> dict:
        try:
            attributes = self._get_connection().getJobAttributes(job_id)
        except RuntimeError as exc:
            logger.exception("Failed to fetch job status for job_id=%s.", job_id)
            raise PrinterError("Unable to read print job status.") from exc

        if not attributes:
            raise PrinterError("Print job not found.")

        state_code = attributes.get("job-state")
        normalized_state = JOB_STATE_MAP.get(state_code, "Failed")
        payload = {
            "job_id": job_id,
            "printer_name": attributes.get("job-printer-uri", "").rsplit("/", 1)[-1] or None,
            "state": normalized_state,
            "state_code": state_code,
            "is_terminal": normalized_state in {"Completed", "Failed"},
            "raw": {
                "job_name": attributes.get("job-name"),
                "job_state_reasons": attributes.get("job-state-reasons"),
            },
        }
        logger.info("Job status for job_id=%s: %s", job_id, payload)
        return payload

    def wait_for_job_completion(
        self, job_id: int, poll_interval: int = 2, timeout: int = 300
    ) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.get_job_status(job_id)
            if status["is_terminal"]:
                return status
            time.sleep(poll_interval)
        raise PrinterError("Timed out waiting for print job completion.")

    def print_pdf(self, printer_name: str, pdf_path: Path, job_name: str) -> int:
        printer_status = self.get_printer_status(printer_name)
        if not printer_status["exists"]:
            raise PrinterError("Selected printer is unavailable.")
        if printer_status["is_stopped"]:
            raise PrinterError("Selected printer is stopped.")

        if not pdf_path.exists():
            raise PrinterError("Printable PDF was not generated.")

        try:
            logger.info(
                "Sending PDF to printer. printer=%s pdf_path=%s job_name=%s",
                printer_name,
                pdf_path,
                job_name,
            )
            job_id = self._get_connection().printFile(
                printer_name,
                str(pdf_path),
                job_name,
                {},
            )
            logger.info("CUPS accepted print job. printer=%s cups_job_id=%s", printer_name, job_id)
            return job_id
        except RuntimeError as exc:
            logger.exception("Print job failed. printer=%s pdf_path=%s", printer_name, pdf_path)
            raise PrinterError("Print job failed.") from exc
