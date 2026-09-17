from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from .one_shot import OneShotMainWindow, install_one_shot_mode
from .ui.cam_tab import CamTab


class MultiFolderMainWindow(OneShotMainWindow):
    """Fenêtre one-shot utilisant le CamTab modulaire multi-dossiers."""

    def rebuild_tabs(self) -> None:
        current_cam: Optional[int] = None
        if self.tabs.currentWidget() is not None:
            for cam, tab in self.cam_tabs.items():
                if tab is self.tabs.currentWidget():
                    current_cam = cam
                    break

        self.clear_tabs_only()
        records = self.filtered_records()
        cams = sorted({record.cam_number for record in records})
        if not cams:
            empty = QLabel("Aucune image CAM trouvée avec la sélection actuelle.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("font-size: 18px; color: white;")
            self.tabs.addTab(empty, "Aucune CAM")
            self.update_active_image_table()
            return

        for cam in cams:
            cam_records = [record for record in records if record.cam_number == cam]
            tab = CamTab(
                cam_number=cam,
                records=cam_records,
                bg_colors=self.bg_colors,
                active_bg_index=self.active_bg_index,
                cache=self.image_cache,
                preload_radius=self.spin_preload_radius.value(),
                preload_enabled=self.chk_global_preload.isChecked(),
                preserve_view_enabled=self.chk_global_preserve.isChecked(),
            )
            tab.shortcut_provider = self
            tab.request_color_select.connect(self.on_bg_selected)
            tab.request_color_edit.connect(self.edit_bg_color)
            tab.request_status_message.connect(lambda msg: self.statusBar().showMessage(msg, 1800))
            tab.current_image_changed.connect(self.on_cam_current_image_changed)
            tab.request_detach_viewer.connect(self.toggle_detached_viewer)
            self.cam_tabs[cam] = tab
            self.tabs.addTab(tab, f"CAM{cam} ({len(cam_records)})")

        if current_cam in self.cam_tabs:
            index = list(self.cam_tabs).index(current_cam)
            self.tabs.setCurrentIndex(index)
        self.update_active_image_table()


def install_multi_folder_mode(app_module) -> None:
    """Active le mode one-shot puis remplace CamTab par l'implémentation modulaire."""
    install_one_shot_mode(app_module)
    app_module.CamTab = CamTab
    app_module.MainWindow = MultiFolderMainWindow
