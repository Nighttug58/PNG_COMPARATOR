"""Compatibilité transitoire : le multi-dossiers est désormais natif dans CamTab."""

from __future__ import annotations

from .one_shot import OneShotMainWindow, install_one_shot_mode


MultiFolderMainWindow = OneShotMainWindow


def install_multi_folder_mode(app_module) -> None:
    install_one_shot_mode(app_module)
