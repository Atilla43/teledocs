import asyncio
import os
import uuid
from datetime import datetime
from pathlib import Path

from docxtpl import DocxTemplate


class DocumentService:
    def __init__(self, templates_dir: str, output_dir: str):
        self.templates_dir = Path(templates_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def generate_document(
        self,
        template_filename: str,
        context: dict,
        user_id: int,
    ) -> tuple[str, str]:
        """Generate a document from template and return (docx_path, pdf_path)."""
        template_path = self.templates_dir / template_filename
        doc = DocxTemplate(str(template_path))

        # Add auto-generated fields
        context["generation_date"] = datetime.now().strftime("%d.%m.%Y")
        context["document_number"] = self._generate_doc_number()

        doc.render(context)

        # Save docx
        unique_id = uuid.uuid4().hex[:8]
        docx_filename = f"{user_id}_{unique_id}.docx"
        docx_path = self.output_dir / docx_filename
        doc.save(str(docx_path))

        # Convert to PDF via LibreOffice headless
        pdf_path = await self._convert_to_pdf(docx_path)

        return str(docx_path), str(pdf_path)

    async def _convert_to_pdf(self, docx_path: Path) -> Path:
        """Convert .docx to .pdf using LibreOffice headless mode."""
        process = await asyncio.create_subprocess_exec(
            "libreoffice",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(self.output_dir),
            str(docx_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()

        pdf_filename = docx_path.stem + ".pdf"
        return self.output_dir / pdf_filename

    def cleanup_files(self, *paths: str) -> None:
        for path in paths:
            try:
                os.remove(path)
            except OSError:
                pass

    @staticmethod
    def _generate_doc_number() -> str:
        return datetime.now().strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:4].upper()
