import json
import re
from pathlib import Path


class TemplateRegistry:
    def __init__(self, templates_dir: str):
        self.templates_dir = Path(templates_dir)
        self._meta: dict = {}
        self._load_metadata()

    def _load_metadata(self) -> None:
        meta_path = self.templates_dir / "template_meta.json"
        if meta_path.exists():
            with open(meta_path, encoding="utf-8") as f:
                self._meta = json.load(f)

    def list_templates(self) -> list[dict]:
        return [
            {
                "id": tid,
                "display_name": tmpl["display_name"],
                "icon": tmpl.get("icon", "📄"),
            }
            for tid, tmpl in self._meta.items()
        ]

    def get_template_meta(self, template_id: str) -> dict | None:
        return self._meta.get(template_id)

    def get_fields(self, template_id: str) -> list[dict]:
        meta = self._meta.get(template_id)
        if not meta:
            return []
        return meta.get("fields", [])

    def get_template_path(self, template_id: str) -> Path | None:
        meta = self._meta.get(template_id)
        if not meta:
            return None
        return self.templates_dir / meta["filename"]

    def validate_field(self, field_meta: dict, value: str) -> str | None:
        """Validate a field value. Returns error message or None if valid."""
        if not value.strip():
            if field_meta.get("required"):
                return f"Поле «{field_meta['label']}» обязательно для заполнения."
            return None  # optional field, empty is OK

        pattern = field_meta.get("validation")
        if pattern and not re.match(pattern, value.strip()):
            return f"Неверный формат для «{field_meta['label']}»."

        return None
