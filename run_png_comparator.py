"""Point d'entrée transitoire de la version modulaire de PNG Comparator.

Pendant le chantier de séparation, l'interface historique reste dans le fichier
V3.01, tandis que les composants déjà extraits sont injectés avant le démarrage.
Cela permet de migrer progressivement sans changer le comportement utilisateur.
"""

from __future__ import annotations

import png_comparator_v3_01_alpha_cleanup as legacy_app

from png_comparator.image_cache import ImageMemoryCache
from png_comparator.models import Annotation, DrawingItem, ImageRecord, ImageScanResult, ViewerState
from png_comparator.scanner import ImageScanner, extract_tags


def install_modular_components() -> None:
    """Branche les composants extraits sur l'application historique.

    Les méthodes des classes historiques résolvent ces symboles dans les globals du
    module au moment de leur exécution. L'injection a donc lieu avant legacy_app.main().
    """

    legacy_app.ImageRecord = ImageRecord
    legacy_app.Annotation = Annotation
    legacy_app.ViewerState = ViewerState
    legacy_app.DrawingItem = DrawingItem
    legacy_app.ImageScanResult = ImageScanResult
    legacy_app.ImageScanner = ImageScanner
    legacy_app.extract_tags = extract_tags
    legacy_app.ImageMemoryCache = ImageMemoryCache


def main() -> int:
    install_modular_components()
    return legacy_app.main()


if __name__ == "__main__":
    raise SystemExit(main())
