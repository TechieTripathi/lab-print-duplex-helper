from pathlib import Path
from uuid import uuid4
import logging

from flask import Flask, jsonify, render_template, request

from services.duplex_service import DuplexService, PrintMode, WorkflowState
from services.pdf_service import PDFService
from services.printer_service import PrinterError, PrinterService


BASE_DIR = Path(__file__).resolve().parent
TMP_DIR = BASE_DIR / "tmp"
UPLOAD_DIR = TMP_DIR / "uploads"
GENERATED_DIR = TMP_DIR / "generated"

for directory in (UPLOAD_DIR, GENERATED_DIR):
    directory.mkdir(parents=True, exist_ok=True)


app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FALLBACK_PRINTERS = [
    "EPSON_M2110_Series_68163E",
    "EPSON_M2110_Series_D9706C",
]
SUPPORTED_EXTENSIONS = {".pdf", ".docx"}

pdf_service = PDFService()
printer_service = PrinterService()
duplex_service = DuplexService(pdf_service, printer_service, GENERATED_DIR)


def format_file_size(size_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    size = float(size_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024


def get_file_extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def is_supported_file(filename: str) -> bool:
    return get_file_extension(filename) in SUPPORTED_EXTENSIONS


def build_pdf_for_workflow(source_path: Path, generated_prefix: str) -> Path:
    if source_path.suffix.lower() == ".pdf":
        return source_path

    converted_pdf_path = GENERATED_DIR / f"{generated_prefix}_converted.pdf"
    converted_pdf = pdf_service.convert_docx_to_pdf(source_path, GENERATED_DIR)
    converted_pdf.replace(converted_pdf_path)
    return converted_pdf_path


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/printers")
def list_printers():
    try:
        printers = printer_service.list_printers()
    except PrinterError as exc:
        payload = {
            "success": False,
            "printers": FALLBACK_PRINTERS,
            "warning": "Printer discovery failed. Showing fallback printers.",
            "error": str(exc),
        }
        logger.warning("GET /api/printers failed. Returning fallback payload: %s", payload)
        return jsonify(payload), 200

    if not printers:
        payload = {
            "success": False,
            "printers": FALLBACK_PRINTERS,
            "warning": "No printers found from CUPS. Showing fallback printers.",
            "error": "No printers found.",
        }
        logger.warning("GET /api/printers found no printers. Returning fallback payload: %s", payload)
        return jsonify(payload), 200

    payload = {"success": True, "printers": printers}
    logger.info("GET /api/printers response payload: %s", payload)
    return jsonify(payload)


@app.get("/api/debug/printers")
def debug_printers():
    try:
        printers = printer_service.list_printers()
        payload = {
            "success": True,
            "printer_count": len(printers),
            "printers": printers,
        }
        logger.info("GET /api/debug/printers response payload: %s", payload)
        return jsonify(payload)
    except PrinterError as exc:
        payload = {
            "success": False,
            "printer_count": 0,
            "printers": FALLBACK_PRINTERS,
            "error": str(exc),
        }
        logger.warning("GET /api/debug/printers failed: %s", payload)
        return jsonify(payload), 500


@app.post("/api/inspect")
def inspect_file():
    file = request.files.get("file")
    if file is None or not file.filename:
        return jsonify({"error": "Please choose a PDF or DOCX file."}), 400

    if not is_supported_file(file.filename):
        return jsonify({"error": "Only PDF and DOCX files are supported."}), 400

    inspect_id = uuid4().hex
    inspect_extension = get_file_extension(file.filename)
    inspect_path = UPLOAD_DIR / f"{inspect_id}_inspect{inspect_extension}"
    file.save(inspect_path)
    converted_pdf_path = GENERATED_DIR / f"{inspect_id}_inspect_converted.pdf"

    try:
        printable_pdf = build_pdf_for_workflow(inspect_path, f"{inspect_id}_inspect")
        total_pages = pdf_service.count_pages(printable_pdf)
        file_size = inspect_path.stat().st_size
    except ValueError as exc:
        inspect_path.unlink(missing_ok=True)
        converted_pdf_path.unlink(missing_ok=True)
        return jsonify({"error": str(exc)}), 400

    inspect_path.unlink(missing_ok=True)
    converted_pdf_path.unlink(missing_ok=True)
    return jsonify(
        {
            "file_name": file.filename,
            "total_pages": total_pages,
            "file_size_bytes": file_size,
            "file_size_label": format_file_size(file_size),
            "file_type": inspect_extension.removeprefix(".").upper(),
        }
    )


@app.post("/api/upload")
def upload_file():
    file = request.files.get("file")
    page_range = (request.form.get("page_range") or "").strip()
    if file is None or not file.filename:
        return jsonify({"error": "Please choose a PDF or DOCX file."}), 400

    if not is_supported_file(file.filename):
        return jsonify({"error": "Only PDF and DOCX files are supported."}), 400

    job_id = uuid4().hex
    upload_extension = get_file_extension(file.filename)
    upload_path = UPLOAD_DIR / f"{job_id}{upload_extension}"
    selected_pdf_path = GENERATED_DIR / f"{job_id}_selected.pdf"
    file.save(upload_path)

    try:
        printable_source_pdf = build_pdf_for_workflow(upload_path, job_id)
        original_total_pages = pdf_service.count_pages(printable_source_pdf)
        selected_page_numbers = pdf_service.parse_page_range(page_range, original_total_pages)
        if len(selected_page_numbers) == original_total_pages:
            printable_pdf = printable_source_pdf
            selected_page_range = "All pages"
        else:
            selected_page_range = pdf_service.format_page_range(selected_page_numbers)
            pdf_service.create_page_range_pdf(printable_source_pdf, selected_pdf_path, selected_page_numbers)
            printable_pdf = selected_pdf_path
        total_pages = len(selected_page_numbers)
    except ValueError as exc:
        upload_path.unlink(missing_ok=True)
        selected_pdf_path.unlink(missing_ok=True)
        return jsonify({"error": str(exc)}), 400

    duplex_service.create_job(
        job_id=job_id,
        original_filename=file.filename,
        source_pdf=printable_pdf,
        total_pages=total_pages,
        original_total_pages=original_total_pages,
        selected_page_range=selected_page_range,
    )

    return jsonify(
        {
            "job_id": job_id,
            "file_name": file.filename,
            "total_pages": total_pages,
            "original_total_pages": original_total_pages,
            "selected_page_range": selected_page_range,
            "adjusted_total_pages": total_pages if total_pages % 2 == 0 else total_pages + 1,
            "print_mode": PrintMode.DUPLEX,
            "state": WorkflowState.IDLE,
        }
    )


@app.get("/api/jobs/<job_id>")
def get_job(job_id: str):
    job = duplex_service.get_job(job_id)
    if job is None:
        return jsonify({"error": "Job not found."}), 404
    return jsonify(job.to_dict())


@app.get("/api/printer/status/<path:printer_name>")
def get_printer_status(printer_name: str):
    try:
        payload = printer_service.get_printer_status(printer_name)
    except PrinterError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(payload)


@app.get("/api/job/status/<int:cups_job_id>")
def get_job_status(cups_job_id: int):
    try:
        payload = printer_service.get_job_status(cups_job_id)
    except PrinterError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(payload)


@app.post("/api/jobs/<job_id>/start")
def start_duplex_print(job_id: str):
    data = request.get_json(silent=True) or {}
    printer_name = data.get("printer_name")
    print_mode = data.get("print_mode", PrintMode.DUPLEX)
    if not printer_name:
        return jsonify({"error": "Printer selection is required."}), 400
    if print_mode not in {PrintMode.SINGLE, PrintMode.DUPLEX}:
        return jsonify({"error": "Invalid print mode."}), 400

    try:
        existing_job = duplex_service.get_job(job_id)
        if existing_job is None:
            return jsonify({"error": "Job not found."}), 404
        existing_job.print_mode = print_mode
        job = duplex_service.start_pass_1(job_id, printer_name)
    except (ValueError, PrinterError) as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(job.to_dict())


@app.post("/api/jobs/<job_id>/continue")
def continue_duplex_print(job_id: str):
    try:
        job = duplex_service.start_pass_2(job_id)
    except (ValueError, PrinterError) as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(job.to_dict())


if __name__ == "__main__":
    app.run(debug=True)
