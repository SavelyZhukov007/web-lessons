from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class ImportDraft(Base):
    __tablename__ = "import_drafts"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(200))
    rows_json: Mapped[str] = mapped_column(Text)
    decisions_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), default="draft")
