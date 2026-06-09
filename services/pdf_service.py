import subprocess
from pathlib import Path

from pypdf import PdfReader, PdfWriter


class PDFService:
    def convert_docx_to_pdf(self, source_path: Path, output_dir: Path) -> Path:
        if source_path.suffix.lower() != ".docx":
            raise ValueError("Only DOCX files can be converted to PDF.")

        output_dir.mkdir(parents=True, exist_ok=True)
        command = [
            "libreoffice",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_dir),
            str(source_path),
        ]

        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False)
        except FileNotFoundError as exc:
            raise ValueError("LibreOffice is not installed, so DOCX files cannot be converted.") from exc

        output_path = output_dir / f"{source_path.stem}.pdf"
        if result.returncode != 0 or not output_path.exists():
            raise ValueError("DOCX to PDF conversion failed.")

        return output_path

    def count_pages(self, pdf_path: Path) -> int:
        try:
            reader = PdfReader(str(pdf_path))
        except Exception as exc:
            raise ValueError("Invalid PDF file.") from exc

        total_pages = len(reader.pages)
        if total_pages == 0:
            raise ValueError("PDF has no pages.")
        return total_pages

    def parse_page_range(self, page_range: str, total_pages: int) -> list[int]:
        cleaned = page_range.strip()
        if not cleaned:
            return list(range(1, total_pages + 1))

        page_numbers: set[int] = set()

        for chunk in cleaned.split(","):
            token = chunk.strip()
            if not token:
                raise ValueError("Page range contains an empty segment.")

            if "-" in token:
                start_text, end_text = token.split("-", 1)
                if not start_text.strip().isdigit() or not end_text.strip().isdigit():
                    raise ValueError("Page ranges must look like 1-3, 5, 8-10.")
                start = int(start_text)
                end = int(end_text)
                if start > end:
                    raise ValueError("Page range start cannot be greater than the end.")
                if start < 1 or end > total_pages:
                    raise ValueError(f"Page range must stay within 1-{total_pages}.")
                page_numbers.update(range(start, end + 1))
                continue

            if not token.isdigit():
                raise ValueError("Page ranges must look like 1-3, 5, 8-10.")

            page_number = int(token)
            if page_number < 1 or page_number > total_pages:
                raise ValueError(f"Page range must stay within 1-{total_pages}.")
            page_numbers.add(page_number)

        normalized_pages = sorted(page_numbers)
        if not normalized_pages:
            raise ValueError("Page range did not include any pages.")
        return normalized_pages

    def format_page_range(self, page_numbers: list[int]) -> str:
        if not page_numbers:
            return ""

        ranges: list[str] = []
        start = page_numbers[0]
        previous = page_numbers[0]

        for page_number in page_numbers[1:]:
            if page_number == previous + 1:
                previous = page_number
                continue

            ranges.append(f"{start}-{previous}" if start != previous else str(start))
            start = previous = page_number

        ranges.append(f"{start}-{previous}" if start != previous else str(start))
        return ", ".join(ranges)

    def create_page_range_pdf(
        self, source_path: Path, output_path: Path, page_numbers: list[int]
    ) -> None:
        reader = PdfReader(str(source_path))
        writer = PdfWriter()

        for page_number in page_numbers:
            writer.add_page(reader.pages[page_number - 1])

        with output_path.open("wb") as output_file:
            writer.write(output_file)

    def ensure_even_page_count(self, source_path: Path, output_path: Path) -> int:
        reader = PdfReader(str(source_path))
        writer = PdfWriter()

        for page in reader.pages:
            writer.add_page(page)

        total_pages = len(reader.pages)
        if total_pages % 2 != 0:
            # Reuse the first page size so the inserted blank page matches the document.
            width = float(reader.pages[0].mediabox.width)
            height = float(reader.pages[0].mediabox.height)
            writer.add_blank_page(width=width, height=height)
            total_pages += 1

        with output_path.open("wb") as output_file:
            writer.write(output_file)

        return total_pages

    def create_even_pdf(self, source_path: Path, output_path: Path) -> None:
        self._create_subset_pdf(source_path, output_path, want_even=True, reverse=False)

    def create_odd_reverse_pdf(self, source_path: Path, output_path: Path) -> None:
        self._create_subset_pdf(source_path, output_path, want_even=False, reverse=True)

    def _create_subset_pdf(
        self, source_path: Path, output_path: Path, want_even: bool, reverse: bool
    ) -> None:
        reader = PdfReader(str(source_path))
        page_numbers = []

        for index in range(len(reader.pages)):
            page_number = index + 1
            if (page_number % 2 == 0) == want_even:
                page_numbers.append(index)

        if reverse:
            # Pass 2 prints odd pages in reverse so the final stack reads normally.
            page_numbers.reverse()

        writer = PdfWriter()
        for index in page_numbers:
            writer.add_page(reader.pages[index])

        with output_path.open("wb") as output_file:
            writer.write(output_file)
