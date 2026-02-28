import os
import re
import uuid
from datetime import datetime
from pathlib import Path

from docxtpl import DocxTemplate
from num2words import num2words


def _format_money(amount_str: str) -> str:
    """Format money: '45000' -> '45 000 (сорок пять тысяч) рублей 00 копеек'."""
    amount_str = amount_str.replace(" ", "").replace(",", ".")
    parts = amount_str.split(".")
    rubles = int(parts[0])
    kopeks = int(parts[1].ljust(2, "0")[:2]) if len(parts) > 1 else 0

    formatted_num = f"{rubles:,}".replace(",", " ")
    rubles_words = num2words(rubles, lang="ru")

    if kopeks:
        kopeks_words = num2words(kopeks, lang="ru")
        return f"{formatted_num} ({rubles_words}) рублей {kopeks:02d} ({kopeks_words}) копеек"
    return f"{formatted_num} ({rubles_words}) рублей 00 копеек"


def _format_report_period(days_str: str) -> str:
    """Format report period: '30' -> '1 (один) отчетный период (30 календарных дней)'."""
    days = int(days_str)
    return f"1 (один) отчетный период ({days} календарных дней)"


def _format_days(days_str: str) -> str:
    """Format days with words: '365' -> '365 (триста шестьдесят пять) календарных дней'."""
    days = int(days_str)
    days_words = num2words(days, lang="ru")
    return f"{days} ({days_words}) календарных дней"


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
    ) -> str:
        """Generate a document from template and return docx_path."""
        template_path = self.templates_dir / template_filename
        doc = DocxTemplate(str(template_path))

        # Add auto-generated fields
        context["generation_date"] = datetime.now().strftime("%d.%m.%Y")
        context["document_number"] = self._generate_doc_number()

        # Extract short name from full company name if not already set
        if "customer_short_name" not in context or not context.get("customer_short_name"):
            company = context.get("customer_company_name", "")
            m = re.search(r"[«\"](.*?)[»\"]", company)
            if m:
                context["customer_short_name"] = m.group(1).title()

        # Format money and period fields
        for key in ("first_period_cost", "subsequent_period_cost"):
            if key in context and context[key]:
                try:
                    context[key] = _format_money(context[key])
                except (ValueError, TypeError):
                    pass
        if "report_period_days" in context and context["report_period_days"]:
            try:
                context["report_period_days_num"] = context["report_period_days"]
                context["report_period_days"] = _format_report_period(
                    context["report_period_days"]
                )
            except (ValueError, TypeError):
                pass
        if "contract_duration_days" in context and context["contract_duration_days"]:
            try:
                context["contract_duration_days"] = _format_days(
                    context["contract_duration_days"]
                )
            except (ValueError, TypeError):
                pass

        # Ensure optional customer fields default to "" so Jinja2 conditionals work
        _OPTIONAL_KEYS = [
            "customer_director_full_name", "customer_address", "customer_phone",
            "customer_kpp", "customer_bank_ks", "customer_bank_bik",
            "customer_bank_name", "customer_city", "customer_short_name",
        ]
        for key in _OPTIONAL_KEYS:
            if key not in context:
                context[key] = ""

        doc.render(context)

        # Save docx
        unique_id = uuid.uuid4().hex[:8]
        docx_filename = f"{user_id}_{unique_id}.docx"
        docx_path = self.output_dir / docx_filename
        doc.save(str(docx_path))

        return str(docx_path)

    def cleanup_files(self, *paths: str) -> None:
        for path in paths:
            try:
                os.remove(path)
            except OSError:
                pass

    @staticmethod
    def _generate_doc_number() -> str:
        return datetime.now().strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:4].upper()
