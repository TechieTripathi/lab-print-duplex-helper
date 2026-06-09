from dataclasses import dataclass
from pathlib import Path

from services.pdf_service import PDFService
from services.printer_service import PrinterError, PrinterService


class WorkflowState:
    IDLE = "IDLE"
    PRINTING_PASS_1 = "PRINTING_PASS_1"
    WAITING_FOR_REINSERT = "WAITING_FOR_REINSERT"
    PRINTING_PASS_2 = "PRINTING_PASS_2"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PrintMode:
    SINGLE = "single"
    DUPLEX = "duplex"


@dataclass
class DuplexJob:
    job_id: str
    original_filename: str
    source_pdf: Path
    total_pages: int
    original_total_pages: int
    selected_page_range: str | None = None
    adjusted_pdf: Path | None = None
    adjusted_total_pages: int | None = None
    printer_name: str | None = None
    print_mode: str = PrintMode.DUPLEX
    state: str = WorkflowState.IDLE
    current_pass: int | None = None
    pass_1_cups_job_id: int | None = None
    pass_2_cups_job_id: int | None = None
    printer_status: str | None = None
    current_job_status: str | None = None
    error_message: str | None = None

    def active_cups_job_id(self) -> int | None:
        if self.state == WorkflowState.PRINTING_PASS_2:
            return self.pass_2_cups_job_id
        if self.state == WorkflowState.PRINTING_PASS_1:
            return self.pass_1_cups_job_id
        return None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "file_name": self.original_filename,
            "total_pages": self.total_pages,
            "original_total_pages": self.original_total_pages,
            "selected_page_range": self.selected_page_range or "All pages",
            "adjusted_total_pages": self.adjusted_total_pages or self.total_pages,
            "printer_name": self.printer_name,
            "print_mode": self.print_mode,
            "state": self.state,
            "current_pass": self.current_pass,
            "pass_1_cups_job_id": self.pass_1_cups_job_id,
            "pass_2_cups_job_id": self.pass_2_cups_job_id,
            "active_cups_job_id": self.active_cups_job_id(),
            "printer_status": self.printer_status,
            "job_status": self.current_job_status,
            "error_message": self.error_message,
        }


class DuplexService:
    def __init__(
        self,
        pdf_service: PDFService,
        printer_service: PrinterService,
        generated_dir: Path,
    ) -> None:
        self.pdf_service = pdf_service
        self.printer_service = printer_service
        self.generated_dir = generated_dir
        self.jobs: dict[str, DuplexJob] = {}

    def create_job(
        self,
        job_id: str,
        original_filename: str,
        source_pdf: Path,
        total_pages: int,
        original_total_pages: int,
        selected_page_range: str | None = None,
    ) -> DuplexJob:
        job = DuplexJob(
            job_id=job_id,
            original_filename=original_filename,
            source_pdf=source_pdf,
            total_pages=total_pages,
            original_total_pages=original_total_pages,
            selected_page_range=selected_page_range,
            printer_status="Ready",
        )
        self.jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> DuplexJob | None:
        job = self.jobs.get(job_id)
        if job is not None:
            self.refresh_job_state(job)
        return job

    def start_pass_1(self, job_id: str, printer_name: str) -> DuplexJob:
        job = self._require_job(job_id)
        if job.state != WorkflowState.IDLE:
            raise ValueError("Job is not ready to start.")

        printer_status = self.printer_service.get_printer_status(printer_name)
        if printer_status["is_stopped"]:
            raise PrinterError("Selected printer is stopped.")

        adjusted_pdf = self.generated_dir / f"{job_id}_adjusted.pdf"
        even_pdf = self.generated_dir / f"{job_id}_even.pdf"

        job.state = WorkflowState.PRINTING_PASS_1
        job.current_pass = 1
        job.printer_name = printer_name
        job.printer_status = printer_status["state"]
        job.error_message = None
        job.current_job_status = "Pending"

        if job.print_mode == PrintMode.SINGLE:
            job.adjusted_total_pages = job.total_pages
            job.pass_1_cups_job_id = self.printer_service.print_pdf(
                printer_name,
                job.source_pdf,
                f"Single-Sided Print - {job.original_filename}",
            )
            return job

        job.adjusted_pdf = adjusted_pdf
        # All later page selection works from an even-page temporary PDF.
        job.adjusted_total_pages = self.pdf_service.ensure_even_page_count(
            job.source_pdf, adjusted_pdf
        )
        self.pdf_service.create_even_pdf(adjusted_pdf, even_pdf)
        job.pass_1_cups_job_id = self.printer_service.print_pdf(
            printer_name,
            even_pdf,
            f"Duplex Pass 1 - {job.original_filename}",
        )
        return job

    def start_pass_2(self, job_id: str) -> DuplexJob:
        job = self._require_job(job_id)
        self.refresh_job_state(job)
        if job.state != WorkflowState.WAITING_FOR_REINSERT:
            raise ValueError("Job is not waiting for paper reinsertion.")
        if job.adjusted_pdf is None or job.printer_name is None:
            raise ValueError("Job is missing pass 1 data.")

        printer_status = self.printer_service.get_printer_status(job.printer_name)
        if printer_status["is_stopped"]:
            raise PrinterError("Selected printer is stopped.")

        odd_pdf = self.generated_dir / f"{job_id}_odd_reverse.pdf"

        job.state = WorkflowState.PRINTING_PASS_2
        job.current_pass = 2
        job.printer_status = printer_status["state"]
        job.current_job_status = "Pending"
        job.error_message = None
        self.pdf_service.create_odd_reverse_pdf(job.adjusted_pdf, odd_pdf)
        job.pass_2_cups_job_id = self.printer_service.print_pdf(
            job.printer_name,
            odd_pdf,
            f"Duplex Pass 2 - {job.original_filename}",
        )
        return job

    def refresh_job_state(self, job: DuplexJob) -> DuplexJob:
        if not job.printer_name:
            return job

        try:
            printer_status = self.printer_service.get_printer_status(job.printer_name)
            job.printer_status = printer_status["state"]
        except PrinterError as exc:
            job.printer_status = "Offline"
            if job.state in {WorkflowState.PRINTING_PASS_1, WorkflowState.PRINTING_PASS_2}:
                job.state = WorkflowState.FAILED
                job.current_job_status = "Failed"
                job.error_message = str(exc)
            return job

        active_job_id = job.active_cups_job_id()
        if active_job_id is None:
            return job

        try:
            job_status = self.printer_service.get_job_status(active_job_id)
            job.current_job_status = job_status["state"]
        except PrinterError as exc:
            job.state = WorkflowState.FAILED
            job.current_job_status = "Failed"
            job.error_message = str(exc)
            return job

        if job.current_job_status == "Completed":
            if job.state == WorkflowState.PRINTING_PASS_1 and job.print_mode == PrintMode.SINGLE:
                job.state = WorkflowState.COMPLETED
            elif job.state == WorkflowState.PRINTING_PASS_1:
                job.state = WorkflowState.WAITING_FOR_REINSERT
            elif job.state == WorkflowState.PRINTING_PASS_2:
                job.state = WorkflowState.COMPLETED
            return job

        if job.current_job_status == "Failed":
            job.state = WorkflowState.FAILED
            job.error_message = "Print job failed."

        return job

    def _require_job(self, job_id: str) -> DuplexJob:
        job = self.jobs.get(job_id)
        if job is None:
            raise ValueError("Job not found.")
        return job
