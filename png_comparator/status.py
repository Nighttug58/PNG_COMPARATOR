from __future__ import annotations

from PySide6.QtGui import QColor

from .models import Annotation


STATUS_DEFAULT = "À contrôler"

STATUS_CHOICES = [
    STATUS_DEFAULT,
    "Terminé",
    "À corriger",
]

STATUS_ALIASES = {
    "A CONTROLER": STATUS_DEFAULT,
    "À CONTROLER": STATUS_DEFAULT,
    "A CONTRÔLER": STATUS_DEFAULT,
    "À CONTRÔLER": STATUS_DEFAULT,
    "NON VERIFIE": STATUS_DEFAULT,
    "NON VÉRIFIÉ": STATUS_DEFAULT,
    "NON VERIFIEE": STATUS_DEFAULT,
    "NON VÉRIFIÉE": STATUS_DEFAULT,
    "NON VÉRIFIÉES": STATUS_DEFAULT,
    "NON VERIFIEES": STATUS_DEFAULT,
    "": STATUS_DEFAULT,
    "OK": "Terminé",
    "TERMINE": "Terminé",
    "TERMINÉ": "Terminé",
    "CORRECTION À FAIRE": "À corriger",
    "CORRECTION A FAIRE": "À corriger",
    "IMAGE À RECOMMENCER": "À corriger",
    "IMAGE A RECOMMENCER": "À corriger",
    "À VÉRIFIER": "À corriger",
    "A VERIFIER": "À corriger",
    "RENDU MANQUANT": "À corriger",
}


def normalize_status(status: str) -> str:
    value = str(status or "").strip()
    if not value:
        return STATUS_DEFAULT
    if value in STATUS_CHOICES:
        return value
    return STATUS_ALIASES.get(value.upper(), "À corriger")


def is_default_status(status: str) -> bool:
    return normalize_status(status) == STATUS_DEFAULT


def status_text_color(status: str) -> QColor:
    value = normalize_status(status)
    if value == "Terminé":
        return QColor(70, 230, 120)
    if value == "À corriger":
        return QColor(255, 90, 90)
    return QColor(255, 215, 70)


def has_annotation_content(annotation: Annotation) -> bool:
    """Return True only when an annotation contains real user information."""
    return bool(
        annotation.marked
        or annotation.comment.strip()
        or not is_default_status(annotation.status)
    )
