# -*- coding: utf-8 -*-
"""FHP multi-view video annotation GUI.

This version is intentionally conservative about Qt so it can run on more
machines (Windows/macOS/Linux/WSL):
  - tries PySide6 -> PyQt6 -> PyQt5 automatically
  - avoids forcing the xcb/wayland Qt platform unless the user asks for it
  - imports Qt before OpenCV to reduce cv2/Qt plugin conflicts
  - remains compatible with Python 3.8+ type syntax

Recommended install:
    python -m pip install PySide6 opencv-python-headless

If you already installed opencv-python and see a Qt plugin conflict, prefer:
    python -m pip uninstall opencv-python opencv-contrib-python
    python -m pip install opencv-python-headless
"""

from __future__ import annotations

import os
import re
import sys
import csv
import io
import json
import math
import platform
import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional

APP_VERSION = "v6.5 FIX SOURCE GROUP DETECTION"
APP_TITLE = f"FHP GUI - {APP_VERSION}"


# ============================================================
# Qt / environment compatibility
# ============================================================

def _is_wsl() -> bool:
    if not sys.platform.startswith("linux"):
        return False
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        return "microsoft" in platform.uname().release.lower()
    except Exception:
        return False


def _library_exists(names: List[str]) -> bool:
    """Return True when at least one shared library name is discoverable.

    This is used before importing Qt.  Qt 6.5+ needs libxcb-cursor0 for the
    xcb platform plugin; forcing xcb without that system package makes the
    app abort before Python can recover.
    """
    try:
        import ctypes.util
        for name in names:
            if ctypes.util.find_library(name):
                return True
    except Exception:
        pass
    return False


def _xcb_runtime_seems_available() -> bool:
    # The user's laptop error explicitly reports missing xcb-cursor0.  Checking
    # this one dependency prevents the most common hard crash when QT_QPA_PLATFORM
    # is forced to xcb on WSL/Ubuntu.
    return _library_exists(["xcb-cursor", "xcb_cursor"])


def configure_qt_environment() -> None:
    """Set robust Qt defaults before importing any Qt binding.

    v5.2 change:
      - On WSL/Wayland, never resize/clamp the top-level window after Save.
        Resizing a natively maximized Wayland window can crash with
        xdg_surface buffer mismatch (e.g., 1430x900 vs 1440x900).

    v5.1 change:
      - Do not blindly force xcb on WSL.  Qt 6.5+ aborts if libxcb-cursor0 is
        missing, which is common on fresh WSL/laptop installs.
      - If xcb runtime deps are present, prefer xcb for WSL stability.
      - If they are missing, let Qt use Wayland/auto so the app still starts.
      - Users can override with FHP_QT_PLATFORM=xcb or FHP_QT_PLATFORM=wayland.
    """
    os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "Round")

    # Mostly Qt5-era variables; keep them conservative for fractional scaling.
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "0")

    forced_platform = os.environ.get("FHP_QT_PLATFORM", "").strip()
    existing_platform = os.environ.get("QT_QPA_PLATFORM", "").strip()
    if forced_platform:
        os.environ["QT_QPA_PLATFORM"] = forced_platform
    elif not existing_platform and _is_wsl():
        if _xcb_runtime_seems_available():
            # XWayland/xcb avoids WSLg Wayland maximized-window buffer mismatch
            # crashes on many desktop monitor setups.
            os.environ["QT_QPA_PLATFORM"] = "xcb"
        else:
            # Critical: do not set QT_QPA_PLATFORM=xcb if libxcb-cursor0 is not
            # installed. Qt would abort before the Python app can show guidance.
            # Leaving it unset lets Qt choose Wayland on WSLg.
            os.environ.pop("QT_QPA_PLATFORM", None)
            os.environ["FHP_XCB_SKIPPED_MISSING_CURSOR"] = "1"

    # OpenCV wheels sometimes point Qt to cv2's own plugin folder, which can
    # conflict with PySide/PyQt. Remove only obviously-cv2 plugin paths.
    for key in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
        value = os.environ.get(key, "")
        if "cv2" in value.lower() or "opencv" in value.lower():
            os.environ.pop(key, None)

    # In pure headless Linux, a GUI cannot be shown. Do not silently force
    # offscreen because users may think the app froze. The startup diagnostic
    # below will print a readable warning instead.


def _load_qt_binding():
    """Try multiple Qt Python bindings and return the classes used below."""
    preferred = os.environ.get("FHP_QT_API", "").strip().lower()
    candidates = []
    if preferred:
        candidates.append(preferred)
    for name in ("pyside6", "pyqt6", "pyqt5"):
        if name not in candidates:
            candidates.append(name)

    errors: List[str] = []

    for name in candidates:
        try:
            if name == "pyside6":
                from PySide6.QtCore import Qt, QTimer, QEvent  # type: ignore
                from PySide6.QtGui import QImage, QPixmap, QPainter, QKeySequence  # type: ignore
                try:
                    from PySide6.QtGui import QShortcut  # type: ignore
                except Exception:
                    from PySide6.QtWidgets import QShortcut  # type: ignore
                from PySide6.QtWidgets import (  # type: ignore
                    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
                    QComboBox, QLineEdit, QCheckBox, QSlider, QFileDialog,
                    QMessageBox, QHBoxLayout, QVBoxLayout, QGridLayout,
                    QGroupBox, QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem, QHeaderView,
                )
                return "PySide6", Qt, QTimer, QEvent, QImage, QPixmap, QPainter, QShortcut, QKeySequence, QApplication, QMainWindow, QWidget, QLabel, QPushButton, QComboBox, QLineEdit, QCheckBox, QSlider, QFileDialog, QMessageBox, QHBoxLayout, QVBoxLayout, QGridLayout, QGroupBox, QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem, QHeaderView

            if name == "pyqt6":
                from PyQt6.QtCore import Qt, QTimer, QEvent  # type: ignore
                from PyQt6.QtGui import QImage, QPixmap, QPainter, QKeySequence  # type: ignore
                try:
                    from PyQt6.QtGui import QShortcut  # type: ignore
                except Exception:
                    from PyQt6.QtWidgets import QShortcut  # type: ignore
                from PyQt6.QtWidgets import (  # type: ignore
                    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
                    QComboBox, QLineEdit, QCheckBox, QSlider, QFileDialog,
                    QMessageBox, QHBoxLayout, QVBoxLayout, QGridLayout,
                    QGroupBox, QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem, QHeaderView,
                )
                return "PyQt6", Qt, QTimer, QEvent, QImage, QPixmap, QPainter, QShortcut, QKeySequence, QApplication, QMainWindow, QWidget, QLabel, QPushButton, QComboBox, QLineEdit, QCheckBox, QSlider, QFileDialog, QMessageBox, QHBoxLayout, QVBoxLayout, QGridLayout, QGroupBox, QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem, QHeaderView

            if name == "pyqt5":
                from PyQt5.QtCore import Qt, QTimer, QEvent  # type: ignore
                from PyQt5.QtGui import QImage, QPixmap, QPainter, QKeySequence  # type: ignore
                try:
                    from PyQt5.QtWidgets import QShortcut  # type: ignore
                except Exception:
                    from PyQt5.QtGui import QShortcut  # type: ignore
                from PyQt5.QtWidgets import (  # type: ignore
                    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
                    QComboBox, QLineEdit, QCheckBox, QSlider, QFileDialog,
                    QMessageBox, QHBoxLayout, QVBoxLayout, QGridLayout,
                    QGroupBox, QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem, QHeaderView,
                )
                return "PyQt5", Qt, QTimer, QEvent, QImage, QPixmap, QPainter, QShortcut, QKeySequence, QApplication, QMainWindow, QWidget, QLabel, QPushButton, QComboBox, QLineEdit, QCheckBox, QSlider, QFileDialog, QMessageBox, QHBoxLayout, QVBoxLayout, QGridLayout, QGroupBox, QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem, QHeaderView
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    msg = "\n".join(errors)
    raise RuntimeError(
        "No supported Qt binding could be imported.\n\n"
        "Install one of these:\n"
        "  python -m pip install PySide6 opencv-python-headless\n"
        "  python -m pip install PyQt6 opencv-python-headless\n"
        "  python -m pip install PyQt5 opencv-python-headless\n\n"
        f"Import errors:\n{msg}"
    )


def _qt_enum(Qt, group_name: str, old_name: str):
    group = getattr(Qt, group_name, None)
    if group is not None and hasattr(group, old_name):
        return getattr(group, old_name)
    return getattr(Qt, old_name)


def _qimage_format_rgb888(QImage):
    fmt = getattr(QImage, "Format_RGB888", None)
    if fmt is not None:
        return fmt
    return getattr(QImage.Format, "Format_RGB888")


def _set_qt_application_attributes(QApplication, Qt) -> None:
    """Set optional app attributes when the binding supports them.

    Qt6 marks AA_EnableHighDpiScaling / AA_UseHighDpiPixmaps as deprecated
    because high-DPI support is enabled by default.  Skip them for Qt6 to avoid
    noisy warnings on the user's laptop.
    """
    if str(globals().get("QT_API", "")).lower().endswith("6"):
        return
    for attr_name, value in (
        ("AA_EnableHighDpiScaling", False),
        ("AA_UseHighDpiPixmaps", True),
    ):
        attr = getattr(Qt, attr_name, None)
        app_attr_group = getattr(Qt, "ApplicationAttribute", None)
        if attr is None and app_attr_group is not None:
            attr = getattr(app_attr_group, attr_name, None)
        if attr is not None:
            try:
                QApplication.setAttribute(attr, value)
            except Exception:
                pass


def _qt_app_exec(app) -> int:
    if hasattr(app, "exec"):
        return app.exec()
    return app.exec_()


def print_startup_diagnostics() -> None:
    display = os.environ.get("DISPLAY", "")
    wayland = os.environ.get("WAYLAND_DISPLAY", "")
    print(f"[startup] Python: {sys.version.split()[0]} | OS: {platform.platform()}")
    print(f"[startup] Qt binding: {QT_API}")
    print(f"[startup] QT_QPA_PLATFORM={os.environ.get('QT_QPA_PLATFORM', '')!r}")
    if os.environ.get("FHP_XCB_SKIPPED_MISSING_CURSOR") == "1":
        print("[startup] xcb was NOT forced because libxcb-cursor0 is missing; using Qt auto/Wayland fallback.")
        print("          To use xcb/XWayland instead: sudo apt install libxcb-cursor0")
    if sys.platform.startswith("linux") and not display and not wayland:
        print("[warning] No DISPLAY/WAYLAND_DISPLAY found. A desktop GUI cannot be shown in this shell.")
        print("          Run from a desktop session, WSLg, VNC, X server, or set FHP_QT_PLATFORM if needed.")


configure_qt_environment()
(
    QT_API, Qt, QTimer, QEvent, QImage, QPixmap, QPainter, QShortcut, QKeySequence,
    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QComboBox, QLineEdit, QCheckBox, QSlider, QFileDialog,
    QMessageBox, QHBoxLayout, QVBoxLayout, QGridLayout,
    QGroupBox, QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem, QHeaderView,
) = _load_qt_binding()

QT_ALIGN_CENTER = _qt_enum(Qt, "AlignmentFlag", "AlignCenter")
QT_ALIGN_LEFT = _qt_enum(Qt, "AlignmentFlag", "AlignLeft")
QT_ALIGN_TOP = _qt_enum(Qt, "AlignmentFlag", "AlignTop")
QT_HORIZONTAL = _qt_enum(Qt, "Orientation", "Horizontal")
QT_STRONG_FOCUS = _qt_enum(Qt, "FocusPolicy", "StrongFocus")
QT_CLICK_FOCUS = _qt_enum(Qt, "FocusPolicy", "ClickFocus")
QT_NO_FOCUS = _qt_enum(Qt, "FocusPolicy", "NoFocus")

def find_optional_header_logo_path() -> str:
    """Find an optional header logo image without making it a required asset.

    Search order:
      1. FHP_HEADER_LOGO environment variable
      2. ./assets/eccv_logo.png next to this script
      3. ./assets/eccv.png, ./assets/header_logo.png, ./assets/logo.png
      4. Same asset names under the current working directory

    If no image exists, the GUI simply hides the logo area and continues.
    """
    names = ["eccv_logo.png", "eccv.png", "header_logo.png", "logo.png", "eccv_logo.jpg", "eccv_logo.jpeg"]
    candidates: List[Path] = []
    env_path = os.environ.get("FHP_HEADER_LOGO", "").strip()
    if env_path:
        candidates.append(Path(env_path).expanduser())
    try:
        script_dir = Path(__file__).resolve().parent
    except Exception:
        script_dir = Path.cwd()
    for base in [script_dir / "assets", Path.cwd() / "assets", script_dir, Path.cwd()]:
        for name in names:
            candidates.append(base / name)
    for cand in candidates:
        try:
            if cand.is_file():
                return str(cand)
        except Exception:
            pass
    return ""


def _env_float(name: str, default: float, lo: float, hi: float) -> float:
    try:
        value = float(os.environ.get(name, "").strip())
        if math.isfinite(value):
            return max(lo, min(hi, value))
    except Exception:
        pass
    return default


def make_translucent_scaled_pixmap(src_pixmap, target_w: int, target_h: int, opacity: float):
    """Return a scaled copy of a logo pixmap with alpha applied.

    This avoids requiring any external image processing dependency and works
    across PySide6/PyQt6/PyQt5.
    """
    try:
        if src_pixmap is None or src_pixmap.isNull():
            return QPixmap()
        target_w = max(1, int(target_w))
        target_h = max(1, int(target_h))
        opacity = max(0.0, min(1.0, float(opacity)))
        scaled = src_pixmap.scaled(target_w, target_h, QT_KEEP_ASPECT_RATIO, QT_SMOOTH_TRANSFORMATION)
        out = QPixmap(scaled.size())
        out.fill(QT_TRANSPARENT)
        painter = QPainter(out)
        painter.setOpacity(opacity)
        painter.drawPixmap(0, 0, scaled)
        painter.end()
        return out
    except Exception:
        return QPixmap()



QT_KEEP_ASPECT_RATIO = _qt_enum(Qt, "AspectRatioMode", "KeepAspectRatio")
QT_SMOOTH_TRANSFORMATION = _qt_enum(Qt, "TransformationMode", "SmoothTransformation")
QT_TRANSPARENT = _qt_enum(Qt, "GlobalColor", "transparent")
QT_WA_TRANSPARENT_FOR_MOUSE_EVENTS = _qt_enum(Qt, "WidgetAttribute", "WA_TransparentForMouseEvents")
QIMAGE_FORMAT_RGB888 = _qimage_format_rgb888(QImage)


def _qevent_type_value(name: str):
    group = getattr(QEvent, "Type", None)
    if group is not None and hasattr(group, name):
        return getattr(group, name)
    return getattr(QEvent, name)


QEVENT_MOUSE_DBLCLICK = _qevent_type_value("MouseButtonDblClick")


def _qt_text_format_value(name: str):
    group = getattr(Qt, "TextFormat", None)
    if group is not None and hasattr(group, name):
        return getattr(group, name)
    return getattr(Qt, name)


def _qt_text_interaction_value(name: str):
    group = getattr(Qt, "TextInteractionFlag", None)
    if group is not None and hasattr(group, name):
        return getattr(group, name)
    return getattr(Qt, name)


QT_PLAIN_TEXT = _qt_text_format_value("PlainText")
QT_TEXT_SELECTABLE_BY_MOUSE = _qt_text_interaction_value("TextSelectableByMouse")


def _size_policy_value(name: str):
    group = getattr(QSizePolicy, "Policy", None)
    if group is not None and hasattr(group, name):
        return getattr(group, name)
    return getattr(QSizePolicy, name)


SP_IGNORED = _size_policy_value("Ignored")
SP_EXPANDING = _size_policy_value("Expanding")
SP_FIXED = _size_policy_value("Fixed")
SP_PREFERRED = _size_policy_value("Preferred")


def _qfiledialog_value(group_name: str, old_name: str, fallback=None):
    """Return QFileDialog enum values across PySide6/PyQt6/PyQt5.

    Qt6 bindings expose many values under nested enum groups, while Qt5 often
    exposes them directly on QFileDialog. This helper keeps the file dialog code
    portable across all supported bindings.
    """
    group = getattr(QFileDialog, group_name, None)
    if group is not None and hasattr(group, old_name):
        return getattr(group, old_name)
    return getattr(QFileDialog, old_name, fallback)


def _dialog_exec(dialog) -> bool:
    """Execute a Qt dialog and return True when accepted."""
    result = dialog.exec() if hasattr(dialog, "exec") else dialog.exec_()
    return bool(result)


def _use_native_file_dialog() -> bool:
    """Allow native dialogs only when explicitly requested.

    On some Linux/WSLg/remote-desktop setups, the native file dialog's path
    combo popup can remain visible after a path is selected. The Qt-managed
    non-native dialog is usually more predictable, so v3.0 uses it by default.
    Set FHP_NATIVE_FILE_DIALOG=1 if the OS-native dialog is preferred.
    """
    return os.environ.get("FHP_NATIVE_FILE_DIALOG", "").strip().lower() in {"1", "true", "yes", "y"}


def _prepare_file_dialog(dialog, directory: str, name_filter: str) -> None:
    """Configure QFileDialog for stable behavior on laptops/desktops/WSL.

    The important choices are:
      - use QFileDialog instance instead of static getOpenFileName calls
      - use DontUseNativeDialog by default
      - keep path history compact so the 'Look in' path dropdown does not leave
        a long floating list on screen after the user changes folders
    """
    try:
        dialog.setModal(True)
    except Exception:
        pass

    opt = _qfiledialog_value("Option", "DontUseNativeDialog")
    if opt is not None:
        try:
            dialog.setOption(opt, not _use_native_file_dialog())
        except Exception:
            pass

    if name_filter:
        try:
            dialog.setNameFilter(name_filter)
        except Exception:
            pass
    if directory:
        try:
            dialog.setDirectory(directory)
        except Exception:
            pass

    detail = _qfiledialog_value("ViewMode", "Detail")
    if detail is not None:
        try:
            dialog.setViewMode(detail)
        except Exception:
            pass

    # The path combo keeps a navigation history. In WSL/Qt combinations this
    # dropdown may stay open awkwardly. Keeping the history compact removes the
    # long persistent path list while preserving normal folder navigation.
    if os.environ.get("FHP_FILE_DIALOG_FULL_HISTORY", "").strip().lower() not in {"1", "true", "yes", "y"}:
        try:
            dialog.setHistory([directory] if directory else [])
        except Exception:
            pass

    # Make the dialog reasonably large, but not dependent on the main window.
    try:
        dialog.resize(900, 600)
    except Exception:
        pass


def choose_save_file(parent, caption: str, directory: str, name_filter: str, default_suffix: str = "") -> str:
    dialog = QFileDialog(parent, caption, directory, name_filter)
    _prepare_file_dialog(dialog, directory, name_filter)
    accept_save = _qfiledialog_value("AcceptMode", "AcceptSave")
    if accept_save is not None:
        try:
            dialog.setAcceptMode(accept_save)
        except Exception:
            pass
    any_file = _qfiledialog_value("FileMode", "AnyFile")
    if any_file is not None:
        try:
            dialog.setFileMode(any_file)
        except Exception:
            pass
    if default_suffix:
        try:
            dialog.setDefaultSuffix(default_suffix)
        except Exception:
            pass
    if not _dialog_exec(dialog):
        return ""
    files = dialog.selectedFiles()
    return files[0] if files else ""


def choose_open_file(parent, caption: str, directory: str, name_filter: str) -> str:
    dialog = QFileDialog(parent, caption, directory, name_filter)
    _prepare_file_dialog(dialog, directory, name_filter)
    existing_file = _qfiledialog_value("FileMode", "ExistingFile")
    if existing_file is not None:
        try:
            dialog.setFileMode(existing_file)
        except Exception:
            pass
    if not _dialog_exec(dialog):
        return ""
    files = dialog.selectedFiles()
    return files[0] if files else ""


def choose_open_files(parent, caption: str, directory: str, name_filter: str) -> List[str]:
    dialog = QFileDialog(parent, caption, directory, name_filter)
    _prepare_file_dialog(dialog, directory, name_filter)
    existing_files = _qfiledialog_value("FileMode", "ExistingFiles")
    if existing_files is not None:
        try:
            dialog.setFileMode(existing_files)
        except Exception:
            pass
    if not _dialog_exec(dialog):
        return []
    return list(dialog.selectedFiles())

try:
    import cv2  # Import after Qt to reduce Qt plugin conflicts.
except Exception as exc:
    raise RuntimeError(
        "OpenCV is required for reading video files.\n"
        "Install it with:\n"
        "  python -m pip install opencv-python-headless\n"
    ) from exc

# ============================================================
# Config
# ============================================================

COLUMNS = [
    "video_id", "session_id", "actor_id", "camera_device",
    "camera_index",
    # yaw_label is the annotation yaw label. For frontal views, it is made
    # capture-set-aware: Rset+Y0 -> YR0, Lset+Y0 -> YL0.
    "yaw_label",
    "framing", "posture", "quality",
    "num_persons", "multi_person", "fps", "resolution",
    "sync_start_frame", "sync_end_frame",
    "annot_start_offset", "annot_end_offset",
    "start_frame", "end_frame", "start_sec", "end_sec",
]

POSTURE_OPTIONS       = ["normal", "fhp", "looking_down"]
QUALITY_OPTIONS       = ["valid", "ambiguous", "invalid"]
NUM_PERSONS_OPTIONS   = ["0", "1", "2", "3+", "unknown"]
MULTI_PERSON_OPTIONS  = ["no", "yes", "unknown"]
CAMERA_DEVICE_OPTIONS = ["unknown", "external_webcam", "desktop_external_webcam", "laptop_builtin", "windows_laptop_builtin", "macbook_builtin", "iphone", "ipad", "android_phone", "tablet"]
FRAMING_OPTIONS       = ["F1_head_shoulder", "F2_chest", "F3_upper_body", "unknown"]
YAW_OPTIONS           = ["", "YR0", "YL0", "Y0", "YL45", "YR45", "YL90", "YR90"]
YAW_DEG_MAP           = {"Y0": 0, "YR0": 0, "YL0": 0, "YL45": -45, "YR45": 45, "YL90": -90, "YR90": 90}

# Default hardware/framing assumptions for the current 3-view FHP capture setup.
# These are only UI defaults; each camera can still be edited manually.
CAMERA_DEFAULTS_BY_INDEX = {
    0: {"device": "external_webcam", "framing": "F2_chest"},          # frontal desktop webcam
    1: {"device": "macbook_builtin", "framing": "F2_chest"},          # 45-degree MacBook view
    2: {"device": "windows_laptop_builtin", "framing": "F3_upper_body"},  # 90-degree Windows laptop, wider upper-body view
}
CAMERA_DEFAULTS_BY_YAW = {
    "Y0": {"device": "external_webcam", "framing": "F2_chest"},
    "YR0": {"device": "external_webcam", "framing": "F2_chest"},
    "YL0": {"device": "external_webcam", "framing": "F2_chest"},
    "YL45": {"device": "macbook_builtin", "framing": "F2_chest"},
    "YR45": {"device": "macbook_builtin", "framing": "F2_chest"},
    "YL90": {"device": "windows_laptop_builtin", "framing": "F3_upper_body"},
    "YR90": {"device": "windows_laptop_builtin", "framing": "F3_upper_body"},
}

def infer_camera_defaults(idx: int, yaw_label: str = "") -> Dict[str, str]:
    yaw = (yaw_label or "").upper().strip()
    defaults = CAMERA_DEFAULTS_BY_YAW.get(yaw) or CAMERA_DEFAULTS_BY_INDEX.get(idx) or {}
    return {
        "device": defaults.get("device", "unknown"),
        "framing": defaults.get("framing", "unknown"),
    }

def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def get_ui_scale() -> float:
    """Return a monitor-aware UI scale.

    v2.8 intentionally capped the scale at 1.08 so laptop layouts would not
    overflow. On large desktop monitors that made the UI look tiny. v2.9 uses
    the available *logical* screen size and allows the interface to grow, while
    keeping a safe lower bound for small laptop screens.

    Manual override is also supported:
        FHP_UI_SCALE=1.35 python fhp_gui_v29_adaptive_font_buttons.py
    """
    override = os.environ.get("FHP_UI_SCALE", "").strip()
    if override:
        try:
            return clamp(float(override), 0.70, 1.80)
        except Exception:
            pass
    try:
        app = QApplication.instance()
        screen = app.primaryScreen() if app is not None else QApplication.primaryScreen()
        if screen is None:
            return 1.0
        geo = screen.availableGeometry()
        w, h = max(1, geo.width()), max(1, geo.height())

        # Designed around ~1500x850 logical pixels.
        dim_scale = min(w / 1500.0, h / 850.0)

        # Logical DPI can indicate OS display scaling. Use it gently because
        # logical screen geometry already reflects many scaling settings.
        dpi = 96.0
        try:
            dpi = float(screen.logicalDotsPerInch())
        except Exception:
            pass
        dpi_factor = clamp(dpi / 96.0, 0.90, 1.30)

        # A soft blend gives FHD laptops reasonable sizes while allowing 2K/4K
        # desktop monitors to grow to readable font/button dimensions.
        scale = (dim_scale ** 0.55) * (dpi_factor ** 0.20)
        return clamp(scale, 0.82, 1.55)
    except Exception:
        return 1.0


def make_stylesheet(ui_scale: float = 1.0) -> str:
    base_font = int(round(clamp(12 * ui_scale, 9, 18)))
    status_font = int(round(clamp(11 * ui_scale, 8, 16)))
    btn_font = int(round(clamp(11 * ui_scale, 8, 17)))
    btn_pad_v = int(round(clamp(4 * ui_scale, 2, 8)))
    btn_pad_h = int(round(clamp(8 * ui_scale, 3, 12)))
    two_line_btn_h = int(round(clamp(42 * ui_scale, 34, 74)))
    single_btn_h = int(round(clamp(30 * ui_scale, 24, 52)))
    radius = int(round(clamp(4 * ui_scale, 3, 8)))
    line_pad_h = int(round(clamp(6 * ui_scale, 3, 10)))
    table_row_pad = int(round(clamp(4 * ui_scale, 2, 8)))

    return f"""
QMainWindow, QWidget {{ background-color: #eef2f7; color: #0f172a; font-size: {base_font}px; }}
QPushButton {{ background-color: #e0e7ff; color: #0f172a; border: 1px solid #cbd5e1; border-radius: {radius}px; padding: {btn_pad_v}px {btn_pad_h}px; font-size: {btn_font}px; font-weight: bold; min-height: {single_btn_h}px; }}
QPushButton#twoLineButton {{ padding: 2px 4px; min-height: {two_line_btn_h}px; }}
QPushButton#tinyButton {{ padding: 2px 3px; min-height: {single_btn_h}px; }}
QPushButton:hover {{ background-color: #c7d2fe; border-color: #4f46e5; }}
QPushButton:pressed {{ background-color: #a5b4fc; }}
QLineEdit, QComboBox {{ background-color: #f8fafc; border: 1px solid #cbd5e1; border-radius: 3px; padding: 3px {line_pad_h}px; }}
QLineEdit#requiredField {{ background-color: #fff7ed; border: 1px solid #f59e0b; }}
QLineEdit[missingRequired="true"] {{ background-color: #fff1f2; border: 2px solid #ef4444; }}
QGroupBox {{ border: 1px solid #cbd5e1; border-radius: 5px; margin-top: 8px; font-weight: bold; color: #4f46e5; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; }}
QLabel#preview {{ background-color: #e2e8f0; color: #64748b; border: 2px solid #e2e8f0; }}
QLabel#preview_active {{ background-color: #e2e8f0; color: #64748b; border: 2px solid #4f46e5; }}
QLabel#camTitle {{ font-weight: bold; }}
QLabel#status {{ color: #334155; font-size: {status_font}px; }}
QLabel#saveLog {{ background-color: #f8fafc; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 5px; padding: 6px 8px; font-size: {status_font}px; font-family: Consolas, "Courier New", monospace; }}
QLabel#saveLog:hover {{ background-color: #eef2ff; border-color: #4f46e5; }}
QWidget#csvPreviewPanel {{ background-color: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px; }}
QLabel#csvPreviewTitle {{ background-color: #eef2ff; color: #0f172a; border-bottom: 1px solid #cbd5e1; padding: 5px 8px; font-size: {base_font}px; font-weight: bold; }}
QLabel#csvPreviewTitle:hover {{ background-color: #e0e7ff; }}
QTableWidget#csvPreviewTable, QTableWidget#csvDialogTable {{ background-color: #ffffff; color: #0f172a; gridline-color: #cbd5e1; font-size: {base_font}px; selection-background-color: #c7d2fe; selection-color: #0f172a; }}
QHeaderView::section {{ background-color: #e2e8f0; color: #0f172a; border: 1px solid #cbd5e1; padding: {table_row_pad}px {line_pad_h}px; font-size: {status_font}px; font-weight: bold; }}
QPushButton#resetButton {{ background-color: #fee2e2; border-color: #fca5a5; color: #7f1d1d; }}
QPushButton#resetButton:hover {{ background-color: #fecaca; border-color: #ef4444; }}
"""

# ============================================================
# Utility
# ============================================================

def safe_float(value, default: float = 0.0) -> float:
    try:
        value = float(value)
        if math.isfinite(value):
            return value
    except Exception:
        pass
    return default


def safe_fps(value, default: float = 30.0) -> float:
    fps = safe_float(value, default)
    if fps <= 1e-6 or fps > 1000:
        return default
    return fps


def open_video_capture(path: str):
    """Open video with a couple of backend fallbacks.

    CAP_FFMPEG helps on many Windows/Linux wheels; CAP_ANY is the final fallback.
    """
    backends = []
    if hasattr(cv2, "CAP_FFMPEG"):
        backends.append(cv2.CAP_FFMPEG)
    backends.append(0)  # CAP_ANY

    last_cap = None
    for backend in backends:
        try:
            cap = cv2.VideoCapture(path, backend) if backend else cv2.VideoCapture(path)
            if cap is not None and cap.isOpened():
                return cap
            if cap is not None:
                cap.release()
            last_cap = cap
        except Exception:
            try:
                if last_cap is not None:
                    last_cap.release()
            except Exception:
                pass
    return cv2.VideoCapture(path)


def frame_to_sec(frame_idx: int, fps: float) -> float:
    if fps <= 0:
        fps = 30.0
    return frame_idx / fps


def sec_to_mmss(sec: float) -> str:
    if sec < 0:
        sec = 0
    m = int(sec // 60)
    s = sec - m * 60
    return f"{m:02d}:{s:05.2f}"


def normalize_video_stem(stem: str) -> List[str]:
    return [t for t in stem.split("_") if t]


def parse_metadata_from_filename(video_path: str) -> dict:
    """Parse subject/action/view metadata from the video filename and path.

    Supported filename styles:
      - S01_A01_YR0.mp4
      - S03_A01_YL0.mp4
      - S04_A03_YL45.mp4
      - S01_act01_Rset_yR90.mp4
      - act01_yR90.mp4

    The first subject token Sxx is used as actor_id.
    The first action token Axx or actxx is used as session_id/action_id.
    """
    video_id = os.path.basename(video_path)
    stem = os.path.splitext(video_id)[0]

    # Use both filename tokens and path components, so S01/A01 can also be
    # detected if the user later creates subject/action folders.
    path_parts = list(Path(os.path.abspath(video_path)).parts)
    raw_tokens = []
    for part in path_parts + [stem]:
        raw_tokens.extend([t for t in re.split(r'[^A-Za-z0-9]+', os.path.splitext(part)[0]) if t])
    tokens = raw_tokens or normalize_video_stem(stem)

    meta = {"video_id": video_id, "actor_id": "", "session_id": "", "yaw_label": "", "framing": ""}

    # actor_id = subject/person id, e.g. S01. Use the first Sxx token found.
    for t in tokens:
        m = re.match(r"^S(\d+)$", t, re.IGNORECASE)
        if m:
            meta["actor_id"] = f"S{int(m.group(1)):02d}"
            break

    # session_id = action id. Support both the new A01 convention and the
    # older act01 convention.
    for t in tokens:
        m = re.match(r"^A(\d+)$", t, re.IGNORECASE)
        if m:
            meta["session_id"] = f"A{int(m.group(1)):02d}"
            break
        m = re.match(r"^act(\d+)$", t, re.IGNORECASE)
        if m:
            meta["session_id"] = f"act{int(m.group(1)):02d}"
            break

    # yaw labels. Prefer explicit YR0/YL0 when present. Y0 is still accepted
    # and will be converted to YR0/YL0 at save-time using the Rset/Lset context.
    for t in tokens:
        tt = t.upper()
        if tt in YAW_DEG_MAP:
            meta["yaw_label"] = tt
            break

    fm = {"F1": "F1_head_shoulder", "F2": "F2_chest", "F3": "F3_upper_body"}
    for t in tokens:
        tt = t.upper()
        if tt in fm:
            meta["framing"] = fm[tt]
            break
    return meta


def ensure_csv_with_headers(csv_path: str):
    """Create or upgrade CSV with the current schema.

    Ensures the CSV has the current schema. Older CSVs are backed up and
    upgraded in-place when needed. Rows previously saved with frontal Y0 under
    Rset/Lset CSV filenames are normalized to YR0/YL0.
    """
    os.makedirs(os.path.dirname(os.path.abspath(csv_path)), exist_ok=True)

    if os.path.exists(csv_path) and os.path.getsize(csv_path) > 0:
        try:
            with open(csv_path, "r", newline="", encoding="utf-8-sig") as f:
                reader = list(csv.reader(f))
            existing_header = reader[0] if reader else []
            existing_rows = reader[1:] if len(reader) > 1 else []
        except Exception:
            existing_header = []
            existing_rows = []

        if existing_header == COLUMNS:
            # v5.7: normalize older rows in-place when the CSV filename already
            # indicates Rset/Lset. This fixes rows previously saved as Y0 under
            # *_Rset_multi_view.csv or *_Lset_multi_view.csv.
            inferred_vs = _infer_view_set_from_paths([csv_path])
            if inferred_vs in {"Rset", "Lset"}:
                changed = False
                normalized_rows = []
                old_index = {name: idx for idx, name in enumerate(existing_header)}
                yaw_idx = old_index.get("yaw_label")
                for row in existing_rows:
                    row = list(row)
                    while len(row) < len(COLUMNS):
                        row.append("")
                    if yaw_idx is not None and yaw_idx < len(row):
                        new_yaw = make_annotation_yaw_label(row[yaw_idx], inferred_vs)
                        if new_yaw != row[yaw_idx]:
                            row[yaw_idx] = new_yaw
                            changed = True
                    normalized_rows.append(row)
                if changed:
                    backup_path = make_timestamped_backup_path(csv_path, suffix="yaw_backup")
                    try:
                        import shutil
                        shutil.copy2(csv_path, backup_path)
                        print(f"[CSV YAW BACKUP] {backup_path}")
                    except Exception as exc:
                        print(f"[CSV YAW BACKUP WARNING] could not create backup: {exc}")
                    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                        writer = csv.writer(f)
                        writer.writerow(COLUMNS)
                        writer.writerows(normalized_rows)
            return

        # If the existing CSV is an older schema or has the same logical fields
        # with missing/new columns, upgrade it in place rather than starting a
        # blank file. This avoids losing already labeled segments.
        if existing_header:
            backup_path = make_timestamped_backup_path(csv_path, suffix="schema_backup")
            try:
                import shutil
                shutil.copy2(csv_path, backup_path)
                print(f"[CSV SCHEMA BACKUP] {backup_path}")
            except Exception as exc:
                print(f"[CSV SCHEMA BACKUP WARNING] could not create backup: {exc}")

            upgraded_rows = []
            old_index = {name: idx for idx, name in enumerate(existing_header)}
            inferred_vs = _infer_view_set_from_paths([csv_path])
            for old_row in existing_rows:
                row_dict = {}
                for col in COLUMNS:
                    if col in old_index:
                        idx = old_index[col]
                        row_dict[col] = old_row[idx] if idx < len(old_row) else ""
                    else:
                        row_dict[col] = ""
                if not row_dict.get("view_set"):
                    row_dict["view_set"] = inferred_vs
                if not row_dict.get("set_yaw_label"):
                    row_dict["set_yaw_label"] = make_annotation_yaw_label(row_dict.get("yaw_label", ""), row_dict.get("view_set", ""))
                upgraded_rows.append(row_dict)

            with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=COLUMNS)
                writer.writeheader()
                for row_dict in upgraded_rows:
                    writer.writerow({col: row_dict.get(col, "") for col in COLUMNS})
            print(f"[CSV SCHEMA UPGRADE] Updated CSV header: {csv_path}")
            return

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        csv.DictWriter(f, fieldnames=COLUMNS).writeheader()

def append_rows_to_csv(csv_path: str, rows: List[Dict[str, object]]):
    ensure_csv_with_headers(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in COLUMNS})


def local_fallback_csv_path(original_csv_path: str) -> str:
    """Return a writable fallback CSV path under the user's home directory.

    This is used when saving next to the video fails, which commonly happens
    when the CSV is open in Excel, the folder is read-only from WSL, or Windows
    Controlled Folder Access blocks writes under Desktop/Documents.
    """
    name = os.path.basename(original_csv_path.strip()) if original_csv_path else "fhp_annotations.csv"
    if not name.lower().endswith(".csv"):
        name += ".csv"
    fallback_dir = os.path.join(str(Path.home()), "fhp_annotations")
    os.makedirs(fallback_dir, exist_ok=True)
    return os.path.join(fallback_dir, name)


def permission_error_hint(path: str, exc: BaseException) -> str:
    return (
        f"Cannot write to CSV:\n{path}\n\n"
        f"Reason: {exc}\n\n"
        "Common causes:\n"
        "1) The CSV is currently open in Excel/LibreOffice. Close it and retry.\n"
        "2) The folder is under Windows Desktop/Documents and WSL does not have write permission.\n"
        "3) Windows security/Controlled Folder Access or cloud sync is blocking the write.\n\n"
        "Choose another CSV location, or cancel the dialog to automatically save to ~/fhp_annotations."
    )


def rows_to_csv_text(rows: List[Dict[str, object]], include_header: bool = True) -> str:
    """Return exactly formatted CSV text for the rows that are about to be saved."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\n")
    if include_header:
        writer.writeheader()
    for row in rows:
        writer.writerow({col: row.get(col, "") for col in COLUMNS})
    return buffer.getvalue().strip()


def read_actual_csv_tail_text(csv_path: str, data_rows: int = 12, include_header: bool = True) -> str:
    """Read the CSV file from disk after saving and return its actual tail text.

    This is intentionally different from formatting the in-memory `rows` object:
    it re-opens the physical CSV file after append, so the preview reflects what
    was truly written to disk.
    """
    try:
        with open(csv_path, "r", newline="", encoding="utf-8-sig") as f:
            text = f.read()
    except Exception as exc:
        return f"[ERROR] Could not read CSV file after saving: {exc}"

    lines = text.splitlines()
    if not lines:
        return "[EMPTY CSV FILE]"

    header = lines[0]
    body = lines[1:]
    n = max(0, int(data_rows))
    selected = body[-n:] if n > 0 else []
    if include_header:
        return "\n".join([header] + selected)
    return "\n".join(selected)


def read_actual_csv_tail_rows(csv_path: str, data_rows: int = 12):
    """Read the real CSV file from disk and return (header, selected_rows).

    This is used for the GUI table preview, so columns line up correctly instead
    of being displayed as a tiny wrapped raw-text block.
    """
    try:
        with open(csv_path, "r", newline="", encoding="utf-8-sig") as f:
            reader = list(csv.reader(f))
    except Exception:
        return [], []
    if not reader:
        return [], []
    header = reader[0]
    body = reader[1:]
    n = max(0, int(data_rows))
    selected = body[-n:] if n > 0 else []
    return header, selected

def read_actual_csv_all_rows(csv_path: str):
    """Return (header, data_rows) from the actual CSV file on disk."""
    try:
        with open(csv_path, "r", newline="", encoding="utf-8-sig") as f:
            reader = list(csv.reader(f))
    except Exception:
        return [], []
    if not reader:
        return [], []
    return reader[0], reader[1:]


def actual_csv_data_row_count(csv_path: str) -> int:
    header, rows = read_actual_csv_all_rows(csv_path)
    return len(rows)


def make_timestamped_backup_path(csv_path: str, suffix: str = "edit_backup") -> str:
    """Return a non-colliding timestamped backup path.

    Cell-level editing can write multiple times within one second, so include
    microseconds and still guard against collisions.
    """
    base, ext = os.path.splitext(csv_path)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    candidate = f"{base}_{suffix}_{stamp}{ext or '.csv'}"
    if not os.path.exists(candidate):
        return candidate
    k = 1
    while True:
        alt = f"{base}_{suffix}_{stamp}_{k}{ext or '.csv'}"
        if not os.path.exists(alt):
            return alt
        k += 1


def write_actual_csv_all_rows(csv_path: str, header, rows, make_backup: bool = True) -> None:
    """Rewrite a CSV safely after editing/deleting rows.

    A timestamped backup is created next to the CSV before replacement so the
    user can recover from accidental edits/deletes.
    """
    csv_path = str(csv_path)
    os.makedirs(os.path.dirname(os.path.abspath(csv_path)), exist_ok=True)
    if make_backup and os.path.exists(csv_path):
        backup_path = make_timestamped_backup_path(csv_path)
        try:
            import shutil
            shutil.copy2(csv_path, backup_path)
            print(f"[CSV BACKUP] {backup_path}")
        except Exception as exc:
            print(f"[CSV BACKUP WARNING] could not create backup: {exc}")
    tmp_path = csv_path + ".tmp"
    with open(tmp_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(list(header or COLUMNS))
        for row in rows:
            writer.writerow(list(row))
    os.replace(tmp_path, csv_path)


def _csv_row_get(row, header, col_name: str) -> str:
    try:
        idx = list(header).index(col_name)
        return str(row[idx]) if idx < len(row) else ""
    except Exception:
        return ""


def _csv_row_set(row, header, col_name: str, value) -> list:
    row = list(row)
    try:
        idx = list(header).index(col_name)
    except ValueError:
        return row
    while len(row) < len(header):
        row.append("")
    row[idx] = str(value)
    return row


def set_table_item_readonly(item):
    """Make a QTableWidgetItem read-only when the Qt binding exposes flags."""
    try:
        item.setFlags(item.flags() & ~_qt_enum(Qt, "ItemFlag", "ItemIsEditable"))
    except Exception:
        pass
    return item


def populate_csv_table(table, header, rows, max_col_width: int = 180, min_col_width: int = 70, editable: bool = False):
    """Populate a QTableWidget with CSV data and cap oversized columns.

    When editable=True, cells can be double-clicked and edited in-place.
    The caller is responsible for connecting itemChanged to the actual CSV
    writer and for blocking signals while the table is being populated.
    """
    header = list(header or [])
    rows = list(rows or [])
    table.clear()
    table.setColumnCount(len(header))
    table.setRowCount(len(rows))
    if header:
        table.setHorizontalHeaderLabels([str(h) for h in header])
    for r, row in enumerate(rows):
        row = list(row)
        for c in range(len(header)):
            value = row[c] if c < len(row) else ""
            text = str(value)
            item = QTableWidgetItem(text)
            if not editable:
                item = set_table_item_readonly(item)
            try:
                tip = "Double-click to edit this CSV cell." if editable else text
                if text:
                    tip += f"\nCurrent value: {text}" if editable else ""
                item.setToolTip(tip)
            except Exception:
                pass
            table.setItem(r, c, item)
    try:
        # v5.0: Do NOT call resizeColumnsToContents() here. With cumulative CSV
        # rows, long filenames/paths/offset summaries can make QTableWidget ask
        # the top-level window for a huge minimum width, which appears as the
        # whole app shifting outside the monitor after Ctrl+S. Use deterministic
        # capped widths and let the table scroll horizontally.
        preferred = {
            "video_id": 130, "session_id": 75, "actor_id": 70,
            "camera_device": 130, "camera_index": 70, "yaw_label": 70,
            "framing": 115, "posture": 95, "quality": 75,
            "num_persons": 80, "multi_person": 85, "fps": 90,
            "resolution": 95, "sync_start_frame": 105, "sync_end_frame": 105,
            "annot_start_offset": 120, "annot_end_offset": 120,
            "start_frame": 85, "end_frame": 85, "start_sec": 80, "end_sec": 80,
        }
        try:
            header_view = table.horizontalHeader()
            header_view.setStretchLastSection(False)
            resize_mode = getattr(QHeaderView, "ResizeMode", QHeaderView)
            header_view.setSectionResizeMode(getattr(resize_mode, "Interactive"))
            if hasattr(header_view, "setMinimumSectionSize"):
                header_view.setMinimumSectionSize(max(36, min_col_width // 2))
            if hasattr(header_view, "setDefaultSectionSize"):
                header_view.setDefaultSectionSize(max(min_col_width, min(max_col_width, 90)))
        except Exception:
            pass
        for c, name in enumerate(header):
            width = preferred.get(str(name), 90)
            width = max(min_col_width, min(max_col_width, int(width)))
            table.setColumnWidth(c, width)
        try:
            table.setMinimumWidth(1)
            table.setSizePolicy(SP_IGNORED, SP_EXPANDING)
        except Exception:
            pass
    except Exception:
        pass
    try:
        table.resizeRowsToContents()
        fm = table.fontMetrics()
        min_h = max(24, fm.height() + 12)
        for r in range(table.rowCount()):
            table.setRowHeight(r, max(min_h, table.rowHeight(r)))
        try:
            table.horizontalHeader().setMinimumHeight(max(24, fm.height() + 12))
        except Exception:
            pass
    except Exception:
        pass


def read_actual_csv_stats(csv_path: str) -> str:
    try:
        with open(csv_path, "r", newline="", encoding="utf-8-sig") as f:
            line_count = sum(1 for _ in f)
        data_rows = max(0, line_count - 1)
        return f"actual_file_rows={data_rows}"
    except Exception as exc:
        return f"actual_file_rows=unknown ({exc})"


def compact_saved_rows_preview(rows: List[Dict[str, object]], max_items: int = 3) -> str:
    """Small one-line summary suitable for the bottom save-log strip."""
    parts = []
    for row in rows[:max_items]:
        parts.append(
            f"cam{row.get('camera_index', '')}:"
            f"{row.get('video_id', '')} "
            f"[{row.get('start_frame', '')}-{row.get('end_frame', '')}] "
            f"{row.get('posture', '')}/{row.get('quality', '')}"
        )
    if len(rows) > max_items:
        parts.append(f"+{len(rows) - max_items} more")
    return " | ".join(parts) if parts else "No rows"


def _extract_action_id_from_paths(paths: List[str]) -> str:
    """Infer a common action/clip id such as A01 or act01 from filenames/paths."""
    for p in paths:
        if not p:
            continue
        stem = os.path.splitext(os.path.basename(p))[0]
        parts = list(Path(os.path.abspath(p)).parts) + [stem]
        for part in parts:
            for token in [t for t in re.split(r'[^A-Za-z0-9]+', os.path.splitext(part)[0]) if t]:
                m = re.match(r"^A(\d+)$", token, re.IGNORECASE)
                if m:
                    return f"A{int(m.group(1)):02d}"
                m = re.match(r"^act(\d+)$", token, re.IGNORECASE)
                if m:
                    return f"act{int(m.group(1)):02d}"
    valid = [p for p in paths if p]
    if valid:
        stem = os.path.splitext(os.path.basename(valid[0]))[0]
        # Fallback: remove common yaw suffixes from the first camera name.
        stem = re.sub(r"_(YR0|YL0|Y0|YL45|YR45|YL90|YR90)$", "", stem, flags=re.IGNORECASE)
        return stem
    return "multiview"


def _extract_subject_id_from_paths(paths: List[str]) -> str:
    """Infer subject id such as S01 from filenames or parent folders.

    v6.4 fix:
    The old implementation used ``\b(S\d+)\b``. In Python regex, underscore
    is a word character, so filenames like ``S01_act03_yR0.mp4`` did NOT match
    because there is no word boundary between ``1`` and ``_``. This made new
    video sets lose ``actor_id`` and produced CSV names such as
    ``act03_Rset_multi_view.csv`` instead of ``S01_act03_Rset_multi_view.csv``.

    We now split every filename/path component on non-alphanumeric separators
    and match full tokens, the same way action ids are parsed.
    """
    for p in paths:
        if not p:
            continue
        parts = list(Path(os.path.abspath(p)).parts)
        parts.append(os.path.splitext(os.path.basename(p))[0])
        for part in parts:
            stem = os.path.splitext(str(part))[0]
            tokens = [t for t in re.split(r'[^A-Za-z0-9]+', stem) if t]
            for token in tokens:
                m = re.match(r"^S(\d+)$", token, re.IGNORECASE)
                if m:
                    return f"S{int(m.group(1)):02d}"
    return ""


def _infer_view_set_from_paths(paths: List[str]) -> str:
    """Infer whether the current 3-camera recording is a right-set or left-set.

    Robust against filenames/folders such as:
      - act01_yr45.mov, act01_yR90.mp4
      - S01_act01_Rset_y0.mp4
      - video_data_FHP/Rset/y0/...
      - video_data_FHP_yR45/yr45_fhp/...

    Returns Rset, Lset, mixed, or empty string.
    """
    has_left = False
    has_right = False
    for p in paths:
        if not p:
            continue
        abs_path = os.path.abspath(str(p))
        parts = list(Path(abs_path).parts)
        # Include both raw components and filename stems so .mp4/.mov suffixes do not
        # break token matching. v5.6 failed for act01_yr45.mov because YR45 was
        # followed by a dot instead of '_'/'-'/'end'.
        candidates = []
        for part in parts:
            candidates.append(part)
            candidates.append(os.path.splitext(part)[0])
        candidates.append(os.path.basename(abs_path))
        candidates.append(os.path.splitext(os.path.basename(abs_path))[0])
        joined = "_".join(candidates).lower()
        tokens = [t for t in re.split(r'[^a-z0-9]+', joined) if t]

        if "lset" in tokens or "yl45" in tokens or "yl90" in tokens:
            has_left = True
        if "rset" in tokens or "yr45" in tokens or "yr90" in tokens:
            has_right = True

        # Extra fallback for compact names that still contain the view string.
        # This catches names like video_data_FHP_yR45 or S01act01YR90 if they appear.
        if re.search(r'yl(?:45|90)', joined, re.IGNORECASE):
            has_left = True
        if re.search(r'yr(?:45|90)', joined, re.IGNORECASE):
            has_right = True
    if has_left and has_right:
        return "mixed"
    if has_left:
        return "Lset"
    if has_right:
        return "Rset"
    return ""


def _infer_view_set_from_yaw_labels(yaw_labels: List[str]) -> str:
    """Infer Rset/Lset from UI yaw labels when path inference is unavailable."""
    has_left = False
    has_right = False
    for y in yaw_labels:
        yy = (y or "").strip().upper()
        if yy in {"YL0", "YL45", "YL90"}:
            has_left = True
        if yy in {"YR0", "YR45", "YR90"}:
            has_right = True
    if has_left and has_right:
        return "mixed"
    if has_left:
        return "Lset"
    if has_right:
        return "Rset"
    return ""


def make_annotation_yaw_label(yaw_label: str, view_set: str) -> str:
    """Return the final yaw_label written to CSV.

    The frontal camera is physically Y0, but in annotation it must preserve
    which synchronized 3-camera set it belongs to:
        Rset + Y0 -> YR0
        Lset + Y0 -> YL0

    Non-frontal labels are kept as-is, e.g. YR45, YL90.
    """
    yaw = (yaw_label or "").strip().upper()
    vs = (view_set or "").strip().lower()
    if yaw in {"YR0", "YL0"}:
        return yaw
    if yaw == "Y0":
        if vs == "rset":
            return "YR0"
        if vs == "lset":
            return "YL0"
    return yaw


def _path_has_yaw_token(path_name: str) -> bool:
    """Return True for directory names such as video_data_FHP_y0, y0_fhp, yR45, yR90."""
    return re.search(r"(^|[_\-])(y0|yl45|yr45|yl90|yr90)([_\-]|$)", path_name, re.IGNORECASE) is not None


def _path_has_viewset_token(path_name: str) -> bool:
    """Return True for capture-set folders/names such as Rset or Lset."""
    return re.search(r"(^|[_\-])(Rset|Lset)([_\-]|$)", path_name, re.IGNORECASE) is not None


def _path_has_capture_specific_token(path_name: str) -> bool:
    """Return True for folders that should not become the annotation root.

    We want annotations under the dataset root, e.g.
        video_data_FHP/annotations/fhp/S01_act01_Rset_multi_view.csv

    even if videos are stored as:
        video_data_FHP/Rset/y0/S01_act01_Rset_y0.mp4
        video_data_FHP/Lset/y0/S01_act01_Lset_y0.mp4
    """
    return _path_has_yaw_token(path_name) or _path_has_viewset_token(path_name)


def _infer_annotation_root_dir(paths: List[str]) -> str:
    """Infer the dataset-level root for annotations.

    Supported layouts include both:

        video_data_FHP/
          video_data_FHP_y0/y0_fhp/...

    and the newer nested set/posture tree used by the user:

        video_data_FHP/
          Rset/y0/fhp/...
          Rset/yR45/fhp/...
          Rset/yR90/fhp/...
          Lset/y0/nhp/...
          Lset/yL45/nhp/...
          Lset/yL90/nhp/...

    In every case, annotation CSVs must be written under:

        video_data_FHP/annotations/...

    rather than inside any source video folder.
    """
    valid = [os.path.abspath(p) for p in paths if p]
    if not valid:
        return os.getcwd()

    # Strongest rule: if a known dataset-root anchor directory (video_data_FHP)
    # appears anywhere in the path, use the highest common such anchor across
    # the loaded camera files. This directly supports trees like:
    #   video_data_FHP/Rset/y0/fhp/file.mp4
    anchor_candidates = []
    for p in valid:
        parts = list(Path(p).parts)
        lowered = [pp.lower() for pp in parts]
        if 'video_data_fhp' in lowered:
            idx = lowered.index('video_data_fhp')
            anchor_candidates.append(str(Path(*parts[:idx+1])))
    if anchor_candidates:
        try:
            return os.path.commonpath(anchor_candidates)
        except Exception:
            return anchor_candidates[0]

    # Fallback: previous generic logic based on common path and capture-specific
    # folder names (yaw/view-set folders such as y0, yR45, yR90, Lset, Rset).
    try:
        common = os.path.commonpath(valid)
        if os.path.isfile(common):
            common = os.path.dirname(common)
    except Exception:
        common = os.path.dirname(valid[0])

    candidate_dirs = []
    for p in valid:
        d = Path(p).parent
        highest_capture_ancestor = None
        for anc in [d] + list(d.parents):
            if _path_has_capture_specific_token(anc.name):
                highest_capture_ancestor = anc
        if highest_capture_ancestor is not None and highest_capture_ancestor.parent:
            candidate_dirs.append(str(highest_capture_ancestor.parent))

    if candidate_dirs:
        try:
            yaw_root = os.path.commonpath(candidate_dirs)
            if len(valid) == 1 or _path_has_capture_specific_token(Path(common).name):
                return yaw_root
            if os.path.commonpath([common, yaw_root]) == yaw_root:
                return common
            return yaw_root
        except Exception:
            return candidate_dirs[0]

    return common


def normalize_actor_id(actor_id: str) -> str:
    """Normalize subject/person id for filenames and CSV rows.

    Convention: actor_id means subject/person, e.g. S01.
    """
    value = (actor_id or "").strip()
    if not value:
        return ""
    m = re.match(r"^s(\d+)$", value, re.IGNORECASE)
    if m:
        return f"S{int(m.group(1)):02d}"
    return value.upper()


def normalize_session_id(session_id: str) -> str:
    """Normalize action/clip id for filenames and CSV rows.

    Convention: session_id means action id. The current preferred notation is
    A01, A02, ... but the older act01 notation is still supported.
    """
    value = (session_id or "").strip()
    if not value:
        return ""
    m = re.match(r"^A(\d+)$", value, re.IGNORECASE)
    if m:
        return f"A{int(m.group(1)):02d}"
    m = re.match(r"^act(\d+)$", value, re.IGNORECASE)
    if m:
        return f"act{int(m.group(1)):02d}"
    return value


def posture_to_annotation_subdir(posture: str) -> str:
    """Map an interval-level posture label to a binary folder name.

    This is now used only as a fallback when the source video folder does not
    reveal whether the loaded clip belongs to an `fhp` or `nhp` capture group.
    In the normal dataset tree, CSV routing is based on the source video folder
    (`.../fhp/...` or `.../nhp/...`), not the posture dropdown.
    """
    value = (posture or "").strip().lower()
    if value in {"fhp", "forward_head_posture"}:
        return "fhp"
    return "nhp"


def _infer_source_annotation_group_from_paths(paths: List[str]) -> str:
    """Infer the CSV folder from the source video tree.

    IMPORTANT v6.5 fix:
    The old exact-component check still had one subtle failure case. If the
    project/repository directory itself was named `fhp`, e.g.

        .../Desktop/fhp/video_data_FHP/Rset/y0/nhp/S01_act01_YR0.mp4

    the path contained both an ancestor component `fhp` and the actual source
    group `nhp`, so the GUI incorrectly reported a mixed fhp/nhp set.

    This function now determines the source group only from the dataset-local
    video tree. In priority order:
      1) components after the dataset root `video_data_FHP`
      2) components after the last view/yaw folder such as y0, yR45, yR90
      3) fallback to the deepest exact component named fhp/nhp

    It therefore ignores unrelated ancestor folders named `fhp`.

    Returns:
        "fhp"   when all loaded video paths belong to an fhp source folder
        "nhp"   when all loaded video paths belong to an nhp source folder
        "mixed" when loaded camera paths contain both source groups
        ""      when the source group cannot be inferred
    """

    def _is_group(part: str) -> str:
        pp = (part or "").strip().lower()
        if pp in {"fhp", "forward_head_posture"}:
            return "fhp"
        if pp in {"nhp", "normal", "normal_head_posture"}:
            return "nhp"
        return ""

    def _is_yaw_or_view_part(part: str) -> bool:
        pp = (part or "").strip()
        return _path_has_yaw_token(pp) or _path_has_viewset_token(pp)

    groups = set()
    for p in paths:
        if not p:
            continue
        try:
            parts = [str(part).strip() for part in Path(os.path.abspath(str(p))).parts]
        except Exception:
            parts = []
        if not parts:
            continue

        lowered = [part.lower() for part in parts]

        # 1) Prefer the dataset-local subtree after video_data_FHP. This avoids
        # treating parent folders like .../Desktop/fhp/... as a source label.
        search_parts = parts
        if "video_data_fhp" in lowered:
            idx = lowered.index("video_data_fhp")
            search_parts = parts[idx + 1:]

        # 2) If there is a yaw/view component, the real source group normally
        # appears after it: Rset/y0/nhp/file.mp4. Use only the tail after the
        # last such component to avoid older naming tokens elsewhere.
        last_yaw_or_view_idx = None
        for i, part in enumerate(search_parts):
            if _is_yaw_or_view_part(part):
                last_yaw_or_view_idx = i
        if last_yaw_or_view_idx is not None:
            tail = search_parts[last_yaw_or_view_idx + 1:]
        else:
            tail = search_parts

        # Prefer the deepest group-like folder in the relevant tail. Deepest is
        # closest to the file and therefore most likely to be the source group.
        group = ""
        for part in reversed(tail):
            group = _is_group(part)
            if group:
                break

        # 3) Fallback: when no dataset root/yaw folder exists, use the deepest
        # exact fhp/nhp component in the entire path. This preserves backward
        # compatibility with older layouts.
        if not group:
            for part in reversed(parts):
                group = _is_group(part)
                if group:
                    break

        if group:
            groups.add(group)

    if len(groups) == 1:
        return next(iter(groups))
    if len(groups) > 1:
        return "mixed"
    return ""


def annotation_subdir_from_source_or_posture(paths: List[str], posture: str = "") -> str:
    """Choose annotations/fhp or annotations/nhp.

    Preferred rule: use the loaded videos' source folder (`fhp` or `nhp`).
    Fallback rule: use the current posture dropdown only when no source folder
    can be inferred, preserving compatibility with older flat folder layouts.
    """
    source_group = _infer_source_annotation_group_from_paths(paths)
    if source_group in {"fhp", "nhp"}:
        return source_group
    return posture_to_annotation_subdir(posture)


def default_csv_path(paths: List[str], actor_id: str = "", session_id: str = "", posture: str = "", view_set: str = "") -> str:
    valid = [p for p in paths if p]
    base_dir = _infer_annotation_root_dir(valid)
    annotation_group = annotation_subdir_from_source_or_posture(valid, posture)
    ann_dir = os.path.join(base_dir, "annotations", annotation_group)
    # Do not create the annotations folder here. Files/folders are created only
    # when the user explicitly saves with Save / Ctrl+S.

    # v6.1 source-folder routing:
    #   actor_id   = subject/person id, e.g. S01
    #   session_id = action/clip id, e.g. act01
    #   annotation folder = source video folder fhp/nhp, not posture dropdown
    #   view_set   = Rset or Lset inferred from loaded yaw views
    #   filename   = S01_act01_Rset_multi_view.csv or S01_act01_Lset_multi_view.csv
    actor_id = normalize_actor_id(actor_id or _extract_subject_id_from_paths(valid))
    session_id = normalize_session_id(session_id or _extract_action_id_from_paths(valid))
    inferred_view_set = (view_set or _infer_view_set_from_paths(valid)).strip()

    if actor_id and session_id and inferred_view_set:
        filename = f"{actor_id}_{session_id}_{inferred_view_set}_multi_view.csv"
    elif actor_id and session_id:
        filename = f"{actor_id}_{session_id}_multi_view.csv"
    elif session_id and inferred_view_set:
        filename = f"{session_id}_{inferred_view_set}_multi_view.csv"
    elif actor_id and inferred_view_set:
        filename = f"{actor_id}_{inferred_view_set}_multi_view.csv"
    elif session_id:
        filename = f"{session_id}_multi_view.csv"
    elif actor_id:
        filename = f"{actor_id}_multi_view.csv"
    else:
        filename = "multi_view.csv"
    return os.path.join(ann_dir, filename)


def default_open_dir() -> str:
    """Use a real desktop folder when available, otherwise current directory."""
    candidates = [
        Path.home() / "Desktop",
        Path.home() / "Downloads",
        Path.cwd(),
    ]
    for p in candidates:
        try:
            if p.exists():
                return str(p)
        except Exception:
            pass
    return os.getcwd()


def app_settings_path() -> Path:
    """Small JSON file used to remember the last opened folders.

    It intentionally lives outside the annotation folder so the GUI remembers
    paths across runs without changing the user's CSV/video data. Users can
    override it with FHP_SETTINGS_PATH when running from shared machines.
    """
    override = os.environ.get("FHP_SETTINGS_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".fhp_gui_settings.json"


def load_app_settings() -> Dict[str, str]:
    path = app_settings_path()
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
    except Exception:
        pass
    return {}


def save_app_settings(settings: Dict[str, str]) -> None:
    path = app_settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"[settings] Could not save settings to {path}: {exc}")


def existing_dir_or_default(path_like: str) -> str:
    """Return a valid directory from a saved file/dir path, or a safe default."""
    if path_like:
        p = Path(str(path_like)).expanduser()
        try:
            if p.is_file():
                p = p.parent
            # Walk upward because removable drives / WSL mounts may disappear.
            while str(p) not in ("", str(p.parent)):
                if p.exists() and p.is_dir():
                    return str(p)
                p = p.parent
            if p.exists() and p.is_dir():
                return str(p)
        except Exception:
            pass
    return default_open_dir()

# ============================================================
# Data
# ============================================================

@dataclass
class CamState:
    path: str = ""
    fps: float = 30.0
    total_frames: int = 0
    width: int = 0
    height: int = 0
    current_frame: int = 0
    sync_start_frame: Optional[int] = None
    sync_end_frame: Optional[int] = None
    yaw_label: str = ""
    cap: Optional[object] = None

    def loaded(self) -> bool:
        return self.cap is not None and bool(self.path) and self.total_frames > 0

# ============================================================
# Clickable Preview
# ============================================================

class CamPreview(QLabel):
    def __init__(self, idx: int, parent=None):
        super().__init__(parent)
        self.idx = idx
        self.app_window = parent
        self.setObjectName("preview")
        self.setAlignment(QT_ALIGN_CENTER)
        # Critical: pixmap must NOT resize the QLabel/layout.
        # The label owns the cell size; video frames are scaled into this box.
        self.setScaledContents(False)
        self.setMinimumSize(1, 1)
        self.setSizePolicy(SP_IGNORED, SP_IGNORED)
        try:
            self.setFocusPolicy(QT_STRONG_FOCUS)
        except Exception:
            pass
        self.setText(f"Cam {idx + 1}\nDouble-click to open")

    def mousePressEvent(self, event):
        if self.app_window is not None:
            self.app_window.select_cam(self.idx)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        # Double-clicking the video preview opens/replaces that camera video.
        if self.app_window is not None:
            self.app_window.select_cam(self.idx)
            self.app_window.open_single_video(self.idx)
            try:
                event.accept()
            except Exception:
                pass
            return
        super().mouseDoubleClickEvent(event)


class TopDoubleClickBar(QWidget):
    """A lightweight top area that toggles maximize/restore on double click.

    Native OS title-bar double-click usually works, but this internal bar gives
    the same behavior in environments where the native window manager is
    inconsistent, such as WSLg, remote desktops, or some Linux themes.
    """
    def __init__(self, app_window=None, parent=None):
        super().__init__(parent)
        self.app_window = app_window

    def mouseDoubleClickEvent(self, event):
        if self.app_window is not None:
            self.app_window.toggle_max_restore()
            try:
                event.accept()
            except Exception:
                pass
            return
        super().mouseDoubleClickEvent(event)


class AutoFitButton(QPushButton):
    """QPushButton that shrinks text only when needed to avoid clipping.

    The global stylesheet makes fonts larger on desktop monitors. If a button
    becomes narrow because the window/layout is constrained, this class chooses
    the largest font size that still fits within the current button rectangle.
    Explicit newlines are respected, so two-line buttons remain readable.
    """
    def __init__(self, text: str, min_px: int = 8, max_px: int = 14, parent=None):
        super().__init__(text, parent)
        self._min_px = int(max(6, min_px))
        self._max_px = int(max(self._min_px, max_px))
        self._last_px = None
        self._fit_text_to_rect()

    def set_fit_range(self, min_px: int, max_px: int):
        self._min_px = int(max(6, min_px))
        self._max_px = int(max(self._min_px, max_px))
        self._fit_text_to_rect()

    def setText(self, text):
        super().setText(text)
        self._fit_text_to_rect()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_text_to_rect()

    def showEvent(self, event):
        super().showEvent(event)
        self._fit_text_to_rect()

    def _fit_text_to_rect(self):
        try:
            text = self.text() or ""
            if not text:
                return
            w = max(1, self.width() - 12)
            h = max(1, self.height() - 8)
            lines = text.splitlines() or [text]

            chosen = self._min_px
            for px in range(self._max_px, self._min_px - 1, -1):
                f = self.font()
                f.setPixelSize(px)
                self.setFont(f)
                fm = self.fontMetrics()
                max_line_w = max(fm.horizontalAdvance(line) for line in lines)
                total_h = fm.lineSpacing() * len(lines)
                if max_line_w <= w and total_h <= h:
                    chosen = px
                    break
            if self._last_px != chosen:
                f = self.font()
                f.setPixelSize(chosen)
                self.setFont(f)
                self._last_px = chosen
        except Exception:
            pass


class SegmentedChoice(QWidget):
    """Small no-popup choice widget used where QComboBox popups can mis-click.

    Some Qt/WSL combinations let a combo-box popup overlap the checkbox below it.
    This widget keeps posture choices always visible, so selecting ``fhp`` cannot
    accidentally toggle ``One person throughout this clip``.
    """
    def __init__(self, options, value=None, ui_scale: float = 1.0, parent=None):
        super().__init__(parent)
        self._options = [str(o) for o in options]
        self._value = str(value if value is not None else (self._options[0] if self._options else ""))
        self._buttons = []
        layout = QHBoxLayout(self)
        try:
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(max(2, int(round(3 * ui_scale))))
        except Exception:
            pass
        max_px = int(round(clamp(11 * ui_scale, 8, 16)))
        min_px = int(round(clamp(8 * ui_scale, 7, 12)))
        for opt in self._options:
            btn = AutoFitButton(opt, min_px=min_px, max_px=max_px)
            btn.setCheckable(True)
            btn.setObjectName("choiceButton")
            btn.setMinimumWidth(0)
            try:
                btn.setSizePolicy(SP_EXPANDING, SP_PREFERRED)
                btn.setMinimumHeight(int(round(clamp(26 * ui_scale, 24, 44))))
            except Exception:
                pass
            btn.clicked.connect(lambda checked=False, v=opt: self.set_value(v))
            self._buttons.append(btn)
            layout.addWidget(btn)
        try:
            self.setMinimumHeight(int(round(clamp(32 * ui_scale, 30, 52))))
        except Exception:
            pass
        self.set_value(self._value)

    def currentText(self):
        return self._value

    def set_value(self, value):
        value = str(value)
        if value not in self._options and self._options:
            value = self._options[0]
        self._value = value
        for btn in self._buttons:
            try:
                btn.setChecked(btn.text().replace("\n", " ") == value or btn.text() == value)
            except Exception:
                pass


class ClickableCsvTitle(QLabel):
    """Clickable title bar for opening the larger actual-CSV viewer."""
    def __init__(self, app_window=None, parent=None):
        super().__init__(parent)
        self.app_window = app_window
        self.setObjectName("csvPreviewTitle")
        self.setText("Actual CSV preview: no rows saved yet. Click here to open larger view.")
        # Important for WSL/XWayland and large monitors: this title text can be
        # very long after saving. If QLabel reports that full text as its
        # minimum width, Qt may expand the whole main window beyond the screen.
        # Keep the title visually compact and store long details as tooltip.
        try:
            self.setSizePolicy(SP_IGNORED, SP_FIXED)
            self.setWordWrap(False)
            self.setMinimumWidth(1)
        except Exception:
            pass

    def set_compact_text(self, text: str, tooltip: str = ""):
        text = str(text or "")
        tooltip = str(tooltip or text)
        try:
            self.setToolTip(tooltip)
        except Exception:
            pass
        try:
            fm = self.fontMetrics()
            # Do not let the label request thousands of pixels because of CSV
            # filenames, camera summaries, or paths. The window is resizable;
            # the full text remains available in the tooltip / large CSV view.
            width = max(260, min(1400, self.width() if self.width() > 50 else 900))
            text = fm.elidedText(text, QT_ELIDE_RIGHT, width)
        except Exception:
            pass
        self.setText(text)

    def mousePressEvent(self, event):
        if self.app_window is not None:
            self.app_window.show_save_log_dialog()
            try:
                event.accept()
            except Exception:
                pass
            return
        super().mousePressEvent(event)


class ActualCsvPreviewPanel(QWidget):
    """Readable bottom preview of rows actually stored in the CSV file."""
    def __init__(self, app_window=None, parent=None):
        super().__init__(parent)
        self.app_window = app_window
        self.setObjectName("csvPreviewPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        bar = QHBoxLayout()
        try:
            bar.setContentsMargins(0, 0, 0, 0)
            bar.setSpacing(4)
        except Exception:
            pass
        layout.addLayout(bar)
        self.title = ClickableCsvTitle(app_window, self)
        bar.addWidget(self.title, stretch=1)
        try:
            s = getattr(app_window, "ui_scale", 1.0) or 1.0
            min_px = int(round(clamp(8 * s, 7, 11)))
            max_px = int(round(clamp(11 * s, 9, 15)))
        except Exception:
            min_px, max_px = 8, 11
        self.btn_apply_metadata = AutoFitButton("Apply\nMetadata", min_px=min_px, max_px=max_px)
        self.btn_apply_metadata.setToolTip("Apply the current metadata panel values to the selected CSV rows. If no row is selected, all rows shown below are updated.")
        self.btn_delete_rows = AutoFitButton("Delete\nRows", min_px=min_px, max_px=max_px)
        self.btn_delete_rows.setObjectName("dangerButton")
        self.btn_delete_rows.setToolTip("Delete the selected CSV rows from the actual CSV file. If no row is selected, all rows shown below are deleted.")
        try:
            self.btn_apply_metadata.clicked.connect(lambda: app_window.apply_current_metadata_to_selected_csv_rows() if app_window is not None else None)
            self.btn_delete_rows.clicked.connect(lambda: app_window.delete_selected_csv_rows() if app_window is not None else None)
        except Exception:
            pass
        bar.addWidget(self.btn_apply_metadata)
        bar.addWidget(self.btn_delete_rows)
        self.table = QTableWidget(0, 0)
        self.table.setObjectName("csvPreviewTable")
        self.table.setWordWrap(False)
        # Never let the bottom CSV table's sizeHint force the main window wider
        # than the monitor. Overflow must stay inside the table via horizontal
        # scrolling / capped columns.
        try:
            self.table.setSizePolicy(SP_IGNORED, SP_EXPANDING)
            self.table.setMinimumWidth(1)
        except Exception:
            pass
        self._updating_table = False
        try:
            self.table.setAlternatingRowColors(True)
            self.table.setShowGrid(True)
            self.table.verticalHeader().setVisible(False)
            self.table.horizontalHeader().setStretchLastSection(False)
            # Cell selection makes direct editing less confusing. Apply/Delete
            # still operates on every row touched by the selected cells.
            if hasattr(self.table, "SelectItems"):
                self.table.setSelectionBehavior(self.table.SelectItems)
            if hasattr(self.table, "ExtendedSelection"):
                self.table.setSelectionMode(self.table.ExtendedSelection)
            # Prefer double-click editing. Keep this guarded for Qt binding differences.
            triggers = []
            for name in ("DoubleClicked", "SelectedClicked", "EditKeyPressed"):
                if hasattr(self.table, name):
                    triggers.append(getattr(self.table, name))
            if triggers:
                val = triggers[0]
                for t in triggers[1:]:
                    val = val | t
                self.table.setEditTriggers(val)
        except Exception:
            pass
        try:
            self.table.itemDoubleClicked.connect(lambda item: self.table.editItem(item))
        except Exception:
            pass
        try:
            self.table.itemChanged.connect(lambda item: self.app_window.handle_csv_preview_item_changed(item) if self.app_window is not None else None)
        except Exception:
            pass
        layout.addWidget(self.table, stretch=1)
        try:
            s = getattr(app_window, "ui_scale", 1.0) or 1.0
            self.setMinimumHeight(int(round(clamp(170 * s, 150, 300))))
            self.setMaximumHeight(int(round(clamp(260 * s, 230, 430))))
            self.setSizePolicy(SP_EXPANDING, SP_FIXED)
        except Exception:
            pass

    def set_rows(self, header, rows, summary: str = "", csv_path: str = ""):
        full_title = summary or "Actual CSV preview"
        if csv_path:
            full_title += "  |  double-click a cell to edit CSV directly; click title to open larger view"
        # Compact visible title: the previous long summary could push the whole
        # application window sideways after the second Ctrl+S. Keep the details
        # in the tooltip / larger view instead.
        shown_rows = len(rows or [])
        if csv_path:
            title = f"CSV view | {os.path.basename(csv_path)} | rows shown: {shown_rows} | double-click cells to edit"
        else:
            title = "Actual CSV preview: no rows saved yet. Click here to open larger view."
        try:
            self.title.set_compact_text(title, full_title)
        except Exception:
            self.title.setText(title)
        self._updating_table = True
        try:
            self.table.blockSignals(True)
        except Exception:
            pass
        try:
            populate_csv_table(self.table, header, rows, max_col_width=170, min_col_width=72, editable=True)
        finally:
            try:
                self.table.blockSignals(False)
            except Exception:
                pass
            self._updating_table = False


class RawCsvViewerWindow(QMainWindow):
    """Separate window with aligned CSV tables plus the raw file text."""
    def __init__(self, title: str, summary: str, appended_header, appended_rows, tail_header, tail_rows, raw_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        try:
            self.resize(1350, 760)
        except Exception:
            pass
        central = QWidget()
        try:
            central.setFocusPolicy(QT_STRONG_FOCUS)
        except Exception:
            pass
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        summary_label = QLabel(summary)
        summary_label.setObjectName("csvPreviewTitle")
        summary_label.setWordWrap(True)
        layout.addWidget(summary_label)

        latest_label = QLabel("Latest appended rows — read back from the actual CSV file")
        latest_label.setObjectName("camTitle")
        layout.addWidget(latest_label)
        latest_table = QTableWidget(0, 0)
        latest_table.setObjectName("csvDialogTable")
        latest_table.setWordWrap(False)
        try:
            latest_table.setAlternatingRowColors(True)
            latest_table.verticalHeader().setVisible(False)
        except Exception:
            pass
        populate_csv_table(latest_table, appended_header, appended_rows, max_col_width=240, min_col_width=90)
        layout.addWidget(latest_table, stretch=2)

        tail_label = QLabel("CSV file tail — also read back from disk")
        tail_label.setObjectName("camTitle")
        layout.addWidget(tail_label)
        tail_table = QTableWidget(0, 0)
        tail_table.setObjectName("csvDialogTable")
        tail_table.setWordWrap(False)
        try:
            tail_table.setAlternatingRowColors(True)
            tail_table.verticalHeader().setVisible(False)
        except Exception:
            pass
        populate_csv_table(tail_table, tail_header, tail_rows, max_col_width=240, min_col_width=90)
        layout.addWidget(tail_table, stretch=2)

        raw_label = QLabel("Raw CSV text block")
        raw_label.setObjectName("camTitle")
        layout.addWidget(raw_label)
        raw = QLabel()
        raw.setObjectName("saveLog")
        raw.setAlignment(QT_ALIGN_LEFT | QT_ALIGN_TOP)
        raw.setWordWrap(False)
        try:
            raw.setTextFormat(QT_PLAIN_TEXT)
            raw.setTextInteractionFlags(QT_TEXT_SELECTABLE_BY_MOUSE)
        except Exception:
            pass
        raw.setText(raw_text)
        
        try:
            raw_px = int(round(clamp(12 * getattr(parent, "ui_scale", 1.0), 10, 18))) if parent is not None else 12
        except Exception:
            raw_px = 12
        raw.setStyleSheet(f'font-family: Consolas, "Courier New", monospace; font-size: {raw_px}px; background-color: #f8fafc; color: #0f172a; padding: 10px;')
        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        try:
            raw.adjustSize()
        except Exception:
            pass
        scroll.setWidget(raw)
        layout.addWidget(scroll, stretch=1)

# ============================================================
# Main Window
# ============================================================

class AnnotationApp(QMainWindow):
    def __init__(self, ui_scale: float = 1.0):
        super().__init__()
        self.ui_scale = ui_scale
        self.setWindowTitle(APP_TITLE)
        try:
            self.setFocusPolicy(QT_STRONG_FOCUS)
        except Exception:
            pass
        self._resize_to_screen()

        self.cams = [CamState() for _ in range(3)]
        self.active_cam = 0
        self.synced_mode = False
        self.global_offset = 0  # shared frame offset from each cam's sync_start_frame
        self.global_offset_sec = 0.0  # shared time offset from each cam's sync_start_frame
        # Default to time sync because the three recordings can have slightly different FPS.
        # T toggles between TIME_SYNC and FRAME_SYNC while in synced annotation mode.
        self.sync_by_time = True
        self.annot_start_offset: Optional[int] = None
        self.annot_end_offset: Optional[int] = None
        self.annot_start_offset_sec: Optional[float] = None
        self.annot_end_offset_sec: Optional[float] = None
        self.saved_count = 0

        # Remember the last folders used for videos and CSVs across runs.
        # This avoids repeatedly navigating from Desktop/Home for Cam 1/2/3.
        self.app_settings = load_app_settings()
        self.last_video_dir = existing_dir_or_default(
            os.environ.get("FHP_LAST_VIDEO_DIR", "") or self.app_settings.get("last_video_dir", "")
        )
        self.last_csv_dir = existing_dir_or_default(
            os.environ.get("FHP_LAST_CSV_DIR", "") or self.app_settings.get("last_csv_dir", "")
        )
        # False means the CSV path is just an automatic suggestion derived
        # from the loaded videos and should be recomputed at Save time after
        # required metadata such as session_id has been filled.
        self.csv_path_manually_selected = False

        self.last_save_log_text = ""
        self.last_save_log_summary = "Save log: no rows saved yet."
        self.last_save_csv_path = ""
        self.last_actual_csv_tail_text = ""
        self.last_actual_appended_text = ""
        self.last_actual_appended_header = []
        self.last_actual_appended_rows = []
        self.last_actual_tail_header = []
        self.last_actual_tail_rows = []
        self.last_preview_start_data_index = 0
        self.last_preview_row_count = 0
        self._raw_csv_viewer_window = None

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._play_step)
        self.is_playing = False

        # Catch double-clicks even when a child QLabel/top-panel receives them.
        # This makes preview double-click and top-bar maximize more reliable
        # across PySide/PyQt, Windows display scaling, WSLg, and remote desktops.
        self._install_global_event_filter()

        self._build_ui()
        self._bind_shortcuts()
        self.select_cam(0)
        self._update_all_status()

    # --------------------------------------------------------
    # UI
    # --------------------------------------------------------
    def _install_global_event_filter(self):
        try:
            app = QApplication.instance()
            if app is not None:
                app.installEventFilter(self)
        except Exception:
            pass

    def _event_pos_in_window(self, obj, event):
        try:
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        except Exception:
            return None
        try:
            if hasattr(obj, "mapTo"):
                return obj.mapTo(self, pos)
        except Exception:
            pass
        return pos

    def _is_interactive_control(self, obj) -> bool:
        return isinstance(obj, (QPushButton, QLineEdit, QComboBox, QCheckBox, QSlider))

    def _is_descendant_of(self, obj, ancestor) -> bool:
        """Return True only when obj is ancestor or one of its Qt children."""
        if obj is None or ancestor is None:
            return False
        try:
            w = obj
            while w is not None:
                if w is ancestor:
                    return True
                w = w.parent() if hasattr(w, "parent") else None
        except Exception:
            pass
        return False

    def _is_inside_file_dialog(self, obj) -> bool:
        """Prevent app-level double-click shortcuts from affecting QFileDialog internals."""
        try:
            w = obj
            while w is not None:
                if isinstance(w, QFileDialog):
                    return True
                w = w.parent() if hasattr(w, "parent") else None
        except Exception:
            pass
        return False

    def eventFilter(self, obj, event):
        try:
            if event.type() == QEVENT_MOUSE_DBLCLICK:
                # Never interpret double-clicks inside QFileDialog as app commands.
                # This fixes the issue where double-clicking the "Look in" area or
                # the file list accidentally maximized/restored the main window.
                if self._is_inside_file_dialog(obj):
                    return super().eventFilter(obj, event)

                # 1) Double-click on any camera preview opens/replaces that camera.
                # Use a strict containment check instead of screen-position heuristics.
                try:
                    for idx, preview in enumerate(getattr(self, "preview_labels", [])):
                        if self._is_descendant_of(obj, preview):
                            self.select_cam(idx)
                            self.open_single_video(idx)
                            event.accept()
                            return True
                except Exception:
                    pass

                # 2) Only the dedicated internal top bar may toggle maximize/restore.
                # Do NOT use a global "y <= top" rule, because modal dialogs such as
                # QFileDialog can also produce coordinates near the top of the main window.
                top_panel = getattr(self, "top_panel", None)
                if self._is_descendant_of(obj, top_panel) and not self._is_interactive_control(obj):
                    self.toggle_max_restore()
                    event.accept()
                    return True
        except Exception:
            pass
        try:
            return super().eventFilter(obj, event)
        except Exception:
            return False

    def _resize_to_screen(self):
        """Start with a window size that fits the current monitor."""
        try:
            screen = QApplication.primaryScreen()
            if screen is None:
                self.resize(1500, 850)
                return
            geo = screen.availableGeometry()
            w = min(1500, max(1000, int(geo.width() * 0.96)))
            h = min(850, max(620, int(geo.height() * 0.92)))
            self.resize(w, h)
        except Exception:
            self.resize(1500, 850)

    def _init_background_watermark(self, central_widget) -> None:
        """Add an optional semi-transparent logo watermark over the GUI.

        The watermark is mouse-transparent, so it never blocks buttons,
        sliders, table editing, or video preview double-clicks. The asset is
        optional; if it is missing, the GUI runs normally without it.

        Put the image at assets/eccv_logo.png next to the script, or set:
            FHP_HEADER_LOGO=/path/to/eccv_logo.png

        Tuning options:
            FHP_LOGO_OPACITY=0.07
            FHP_LOGO_SCALE=0.42
        """
        self.background_logo_label = None
        self.background_logo_pixmap = None
        self.background_logo_path = ""
        try:
            logo_path = find_optional_header_logo_path()
            if not logo_path:
                return
            pix = QPixmap(logo_path)
            if pix.isNull():
                return
            self.background_logo_path = logo_path
            self.background_logo_pixmap = pix
            label = QLabel(central_widget)
            label.setObjectName("backgroundLogoWatermark")
            label.setAlignment(QT_ALIGN_CENTER)
            label.setStyleSheet("background: transparent;")
            label.setToolTip("Optional semi-transparent background logo watermark")
            try:
                label.setAttribute(QT_WA_TRANSPARENT_FOR_MOUSE_EVENTS, True)
            except Exception:
                pass
            try:
                label.setSizePolicy(SP_IGNORED, SP_IGNORED)
            except Exception:
                pass
            self.background_logo_label = label
            self._update_background_watermark()
            print(f"[startup] Background logo watermark: {logo_path}")
        except Exception as exc:
            print(f"[startup] Background logo watermark disabled: {exc}")
            self.background_logo_label = None
            self.background_logo_pixmap = None

    def _update_background_watermark(self) -> None:
        try:
            label = getattr(self, "background_logo_label", None)
            src = getattr(self, "background_logo_pixmap", None)
            central = self.centralWidget()
            if label is None or src is None or central is None or src.isNull():
                return
            cw = max(1, central.width())
            ch = max(1, central.height())
            label.setGeometry(0, 0, cw, ch)

            scale = _env_float("FHP_LOGO_SCALE", 0.42, 0.12, 0.85)
            opacity = _env_float("FHP_LOGO_OPACITY", 0.075, 0.0, 0.35)
            target_w = int(cw * scale)
            target_h = int(ch * scale)
            pix = make_translucent_scaled_pixmap(src, target_w, target_h, opacity)
            if not pix.isNull():
                label.setPixmap(pix)
                label.show()
                # Use a mouse-transparent overlay so the watermark remains
                # visible even though most child widgets have solid backgrounds.
                # It does not intercept clicks or keyboard focus.
                label.raise_()
        except Exception:
            pass

    def resizeEvent(self, event):
        try:
            super().resizeEvent(event)
        except Exception:
            pass
        self._update_background_watermark()

    def _safe_resize_like_maximized(self):
        """Pseudo-maximize without asking Wayland for native maximized state.

        Native showMaximized() can trigger WSLg/Wayland buffer mismatch crashes
        during heavy redraws.  This keeps the convenience of a large window while
        avoiding the fragile native maximized state.
        """
        try:
            screen = self.screen() or QApplication.primaryScreen()
            geo = screen.availableGeometry() if screen is not None else None
            if geo is None:
                self.resize(1500, 850)
                return
            margin = max(12, int(round(12 * getattr(self, "ui_scale", 1.0))))
            self.setGeometry(
                geo.x() + margin,
                geo.y() + margin,
                max(900, geo.width() - 2 * margin),
                max(600, geo.height() - 2 * margin),
            )
        except Exception:
            self.resize(1500, 850)

    def _running_on_wayland(self) -> bool:
        try:
            platform_name = str(os.environ.get("QT_QPA_PLATFORM", "")).lower()
            # When QT_QPA_PLATFORM is unset on WSLg, Qt usually auto-selects wayland.
            return "wayland" in platform_name or (not platform_name and bool(os.environ.get("WAYLAND_DISPLAY")))
        except Exception:
            return False

    def _clamp_window_to_screen(self):
        """Keep the window inside the monitor only when it is safe.

        v5.2 important fix:
        On WSLg/Wayland, calling setGeometry()/resize() while the top-level
        window is in the compositor's *maximized* state can hard-crash Qt with:

            xdg_surface buffer (...) does not match the configured maximized state

        Therefore this method is a no-op on Wayland or when the window is
        maximized/fullscreen.  It is used only on xcb/non-Wayland setups where
        post-save table refresh could otherwise push the window outside screen.
        """
        try:
            if self._running_on_wayland() or self.isMaximized() or self.isFullScreen():
                return
            screen = self.screen() or QApplication.primaryScreen()
            if screen is None:
                return
            geo = screen.availableGeometry()
            g = self.geometry()
            margin = max(8, int(round(8 * getattr(self, "ui_scale", 1.0))))
            max_w = max(900, geo.width() - 2 * margin)
            max_h = max(560, geo.height() - 2 * margin)
            w = min(max(g.width(), 900), max_w)
            h = min(max(g.height(), 560), max_h)
            x = min(max(g.x(), geo.x() + margin), geo.x() + geo.width() - w - margin)
            y = min(max(g.y(), geo.y() + margin), geo.y() + geo.height() - h - margin)
            # Do not set geometry if nothing changes; it avoids needless
            # compositor negotiations during heavy CSV table refresh.
            if (g.x(), g.y(), g.width(), g.height()) != (x, y, w, h):
                self.setGeometry(x, y, w, h)
        except Exception:
            pass

    def _clamp_window_to_screen_later(self):
        # v5.2: no delayed geometry changes on Wayland/maximized windows.
        try:
            if self._running_on_wayland() or self.isMaximized() or self.isFullScreen():
                return
            QTimer.singleShot(0, self._clamp_window_to_screen)
            QTimer.singleShot(120, self._clamp_window_to_screen)
        except Exception:
            self._clamp_window_to_screen()

    def _should_avoid_native_maximize(self) -> bool:
        platform_name = os.environ.get("QT_QPA_PLATFORM", "").lower()
        return _is_wsl() or "wayland" in platform_name

    def toggle_max_restore(self):
        """Toggle between large/safe and normal window size."""
        # On WSL/Wayland, never call showMaximized(); use a safe pseudo-maximize
        # instead.  This prevents xdg_surface buffer mismatch crashes after Save.
        if self._should_avoid_native_maximize():
            if getattr(self, "_pseudo_maximized", False):
                try:
                    self.showNormal()
                    normal_geo = getattr(self, "_normal_geometry_before_pseudo_max", None)
                    if normal_geo is not None:
                        self.setGeometry(normal_geo)
                except Exception:
                    self.resize(1500, 850)
                self._pseudo_maximized = False
            else:
                try:
                    self._normal_geometry_before_pseudo_max = self.geometry()
                except Exception:
                    self._normal_geometry_before_pseudo_max = None
                self._safe_resize_like_maximized()
                self._pseudo_maximized = True
            return

        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def mouseDoubleClickEvent(self, event):
        """Do not globally maximize on arbitrary top-area double-clicks.

        v4.7 intentionally leaves maximize/restore to the dedicated top-panel
        event filter only.  A broad y-coordinate fallback caused unrelated
        dialogs/widgets to interact badly with WSLg/Wayland.
        """
        super().mouseDoubleClickEvent(event)

    def _button(self, text: str, tooltip: Optional[str] = None, multiline: bool = False, tiny: bool = False) -> object:
        """Create a compact, stretchable button for small laptop screens.

        Qt does not automatically word-wrap QPushButton text. For controls with
        longer labels, pass multiline=True and provide text with either spaces or
        an explicit ``\n``. This avoids clipping under Windows/macOS display
        scaling and on small laptop panels.
        """
        display_text = text
        if multiline and "\n" not in display_text:
            parts = display_text.split()
            if len(parts) >= 2:
                mid = max(1, len(parts) // 2)
                display_text = " ".join(parts[:mid]) + "\n" + " ".join(parts[mid:])
        max_px = int(round(clamp((11 if tiny else 12) * self.ui_scale, 8, 17)))
        min_px = int(round(clamp(8 * self.ui_scale, 7, 12)))
        btn = AutoFitButton(display_text, min_px=min_px, max_px=max_px)
        btn.setMinimumWidth(0)
        line_count = max(1, display_text.count("\n") + 1)
        if multiline:
            btn.setObjectName("twoLineButton")
        elif tiny:
            btn.setObjectName("tinyButton")
        try:
            target_h = (max_px * 1.85) if line_count == 1 else (max_px * line_count * 1.55 + 10)
            btn.setMinimumHeight(int(round(clamp(target_h, 26, 82))))
        except Exception:
            pass
        try:
            # Let all buttons grow vertically if the monitor scale is large.
            # AutoFitButton will shrink text only when the allocated rectangle
            # is too small, preventing clipped labels.
            btn.setSizePolicy(SP_EXPANDING, SP_PREFERRED)
        except Exception:
            pass
        if tooltip:
            btn.setToolTip(tooltip)
        elif len(text) > 10:
            btn.setToolTip(text.replace("\n", " "))
        return btn

    def _apply_compact_widget_defaults(self, widget) -> None:
        try:
            widget.setMinimumWidth(0)
            widget.setSizePolicy(SP_EXPANDING, SP_FIXED)
        except Exception:
            pass

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        self._init_background_watermark(central)
        root = QVBoxLayout(central)
        m = max(4, int(round(6 * self.ui_scale)))
        root.setContentsMargins(m, m, m, m)
        root.setSpacing(max(3, int(round(5 * self.ui_scale))))

        self.top_panel = TopDoubleClickBar(self, central)
        self.top_panel.setToolTip("Double-click here to maximize/restore the window")
        top_panel = self.top_panel
        top = QHBoxLayout(top_panel)
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(max(3, int(round(4 * self.ui_scale))))
        self.btn_open3 = self._button("Open 3", "Open 3 Videos")
        self.btn_csv = self._button("CSV", "Choose CSV path (file is created only when you press Save / Ctrl+S)")
        self.edit_csv = QLineEdit()
        self.edit_csv.setReadOnly(True)
        self.edit_csv.setPlaceholderText("CSV will be created only when you press Save / Ctrl+S")
        self.btn_open3.clicked.connect(self.open_three_videos)
        self.btn_csv.clicked.connect(self.choose_csv)
        top.addWidget(self.btn_open3)
        top.addWidget(self.btn_csv)
        top.addWidget(QLabel("CSV path:"))
        top.addWidget(self.edit_csv, stretch=1)

        # v6.2: ECCV/logo asset is now shown as a semi-transparent
        # background watermark instead of a small header icon. This keeps the
        # top toolbar compact while preserving the original visual identity.

        root.addWidget(self.top_panel)

        body = QHBoxLayout()
        root.addLayout(body, stretch=1)

        left = QVBoxLayout()
        body.addLayout(left, stretch=1)

        grid = QGridLayout()
        grid.setSpacing(max(3, int(round(4 * self.ui_scale))))
        grid.setRowStretch(1, 1)
        for _col in range(3):
            grid.setColumnStretch(_col, 1)
        left.addLayout(grid, stretch=1)

        self.title_labels = []
        self.preview_labels = []
        self.local_frame_edits = []
        self.btn_open_cam = []
        self.btn_sync_start = []
        self.btn_sync_end = []

        for i in range(3):
            title = QLabel(f"▶ Cam {i + 1} - not loaded")
            title.setObjectName("camTitle")
            title.setAlignment(QT_ALIGN_CENTER)
            grid.addWidget(title, 0, i)
            self.title_labels.append(title)

            preview = CamPreview(i, self)
            grid.addWidget(preview, 1, i)
            self.preview_labels.append(preview)

            bar = QHBoxLayout()
            bar.setSpacing(max(2, int(round(3 * self.ui_scale))))
            bopen = self._button("Open", f"Open Cam {i + 1}", tiny=False)
            # Keep the per-camera Open button readable on large monitors and
            # prevent the local-frame box from stealing all horizontal space.
            open_w = int(round(clamp(96 * self.ui_scale, 82, 165)))
            local_w = int(round(clamp(165 * self.ui_scale, 135, 265)))
            try:
                bopen.setMinimumWidth(open_w)
                bopen.setFixedWidth(open_w)
                bopen.setSizePolicy(SP_FIXED, SP_PREFERRED)
            except Exception:
                pass
            edit = QLineEdit()
            edit.setReadOnly(True)
            edit.setPlaceholderText("local frame")
            try:
                edit.setMinimumWidth(local_w)
                edit.setMaximumWidth(local_w)
                edit.setSizePolicy(SP_FIXED, SP_FIXED)
            except Exception:
                self._apply_compact_widget_defaults(edit)
            bopen.clicked.connect(lambda checked=False, idx=i: self.open_single_video(idx))
            # v3.2+ workflow:
            #   - Enter Sync captures sync_start_frame for all loaded cameras.
            #   - End (E) captures sync_end_frame for all loaded cameras.
            # Therefore per-camera Sync S/E buttons are intentionally removed.
            bar.addWidget(bopen, stretch=0)
            bar.addWidget(edit, stretch=0)
            bar.addStretch(1)
            grid.addLayout(bar, 2, i)
            self.btn_open_cam.append(bopen)
            self.local_frame_edits.append(edit)

        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("status")
        try:
            self.status_label.setSizePolicy(SP_IGNORED, SP_FIXED)
            self.status_label.setMinimumWidth(1)
        except Exception:
            pass
        left.addWidget(self.status_label)

        self.slider = QSlider(QT_HORIZONTAL)
        self.slider.setMinimum(0)
        self.slider.setMaximum(1)
        self.slider.sliderReleased.connect(self._slider_released)
        self.slider.sliderMoved.connect(self._slider_moved)
        left.addWidget(self.slider)

        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(max(4, int(round(6 * self.ui_scale))))
        ctrl = QGridLayout()
        ctrl.setSpacing(max(2, int(round(4 * self.ui_scale))))
        self.ctrl_cols = 5
        for _col in range(self.ctrl_cols):
            ctrl.setColumnStretch(_col, 1)
        self.btn_minus5s = self._button("-5s", "-5s (Shift+Z)", tiny=True)
        self.btn_minus1s = self._button("-1s", "-1s (Z)", tiny=True)
        self.btn_prev = self._button("Prev", "Prev frame (A)", tiny=True)
        self.btn_play = self._button("Play", "Play/Pause (Space)", tiny=True)
        self.btn_next = self._button("Next", "Next frame (D)", tiny=True)
        self.btn_plus1s = self._button("+1s", "+1s (C)", tiny=True)
        self.btn_plus5s = self._button("+5s", "+5s (Shift+C)", tiny=True)
        self.btn_enter_sync = self._button("Enter\nSync", "Enter Synced Annotation Mode", multiline=True)
        self.btn_exit_sync = self._button("Exit\nSync", "Exit Sync Mode", multiline=True)
        self.btn_reset_active = self._button("Reset\nCam", "Reset Active Sync (R)", multiline=True)
        self.btn_reset_all = self._button("Reset\nAll", "Reset All Sync (Ctrl+R)", multiline=True)
        self.btn_reset_active.setObjectName("resetButton")
        self.btn_reset_all.setObjectName("resetButton")
        self.btn_set_start = self._button("Start\n(Q)", "Set Start (Q)", multiline=True)
        self.btn_set_end = self._button("End\n(E)", "Set End (E)", multiline=True)
        self.btn_save = self._button("Save", "Save Rows (Ctrl+S)", tiny=True)

        self.btn_minus5s.clicked.connect(lambda: self.jump_seconds(-5))
        self.btn_minus1s.clicked.connect(lambda: self.jump_seconds(-1))
        self.btn_prev.clicked.connect(lambda: self.step_frame(-1))
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_next.clicked.connect(lambda: self.step_frame(1))
        self.btn_plus1s.clicked.connect(lambda: self.jump_seconds(1))
        self.btn_plus5s.clicked.connect(lambda: self.jump_seconds(5))
        self.btn_enter_sync.clicked.connect(self.enter_synced_mode)
        self.btn_exit_sync.clicked.connect(self.exit_synced_mode)
        self.btn_reset_active.clicked.connect(self.reset_active_sync)
        self.btn_reset_all.clicked.connect(self.reset_all_sync)
        self.btn_set_start.clicked.connect(self.set_annotation_start)
        self.btn_set_end.clicked.connect(self.set_annotation_end)
        self.btn_save.clicked.connect(self.save_annotation)

        ctrl_items = [
            self.btn_minus5s, self.btn_minus1s, self.btn_prev, self.btn_play, self.btn_next,
            self.btn_plus1s, self.btn_plus5s, self.btn_enter_sync, self.btn_exit_sync,
            self.btn_set_start, self.btn_set_end, self.btn_save,
        ]
        for pos, w in enumerate(ctrl_items):
            ctrl.addWidget(w, pos // self.ctrl_cols, pos % self.ctrl_cols)

        reset_box = QVBoxLayout()
        reset_box.setSpacing(max(2, int(round(4 * self.ui_scale))))
        reset_box.addWidget(self.btn_reset_active)
        reset_box.addWidget(self.btn_reset_all)
        reset_box.addStretch(1)
        ctrl_row.addLayout(ctrl, stretch=1)
        ctrl_row.addLayout(reset_box, stretch=0)
        left.addLayout(ctrl_row)

        # Right form
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_w = int(round(clamp(300 * self.ui_scale, 245, 430)))
        right_scroll.setMinimumWidth(max(230, right_w - 20))
        right_scroll.setMaximumWidth(right_w)
        right_widget = QWidget()
        right_scroll.setWidget(right_widget)
        body.addWidget(right_scroll)
        form = QVBoxLayout(right_widget)

        grp = QGroupBox("Common Annotation Metadata")
        gl = QGridLayout(grp)
        form.addWidget(grp)
        self.fields = {}

        def add_entry(label, key, row, readonly=False, required=False):
            shown_label = f"{label} *" if required and not str(label).endswith("*") else label
            label_widget = QLabel(shown_label)
            if required:
                label_widget.setToolTip("Required before saving")
            gl.addWidget(label_widget, row, 0)
            w = QLineEdit()
            w.setReadOnly(readonly)
            if required:
                w.setObjectName("requiredField")
                w.setPlaceholderText("required")
                w.setToolTip("Required before saving")
                w.setProperty("missingRequired", "false")
            try:
                # Press Enter after typing metadata to return to navigation mode,
                # so A/D/Z/C/Q/E shortcuts do not get typed into this field.
                w.returnPressed.connect(lambda: QTimer.singleShot(0, self._focus_navigation_mode))
            except Exception:
                pass
            gl.addWidget(w, row, 1)
            self.fields[key] = w

        def add_combo(label, key, row, opts):
            gl.addWidget(QLabel(label), row, 0)
            w = QComboBox()
            w.addItems(opts)
            try:
                w.setMaxVisibleItems(min(max(len(opts), 3), 6))
            except Exception:
                pass
            try:
                # After selecting dropdown metadata, return focus to the main
                # annotation window so navigation shortcuts work immediately.
                w.activated.connect(lambda *_: QTimer.singleShot(0, self._focus_navigation_mode))
            except Exception:
                pass
            gl.addWidget(w, row, 1)
            self.fields[key] = w

        row = 0
        add_entry("session_id (act_id)", "session_id", row, required=True); row += 1
        add_entry("actor_id (subject)", "actor_id", row, required=True); row += 1

        # v4.2: camera_device and framing are per-camera fields, not common fields.
        # In this capture setup, the frontal/45-degree views are chest-level,
        # while the 90-degree view uses a wider upper-body framing. The camera hardware also
        # differs across views. Each row in the CSV stores its own camera metadata.
        for i in range(3):
            add_combo(f"cam{i+1}_device", f"cam{i+1}_device", row, CAMERA_DEVICE_OPTIONS); row += 1
            add_combo(f"cam{i+1}_framing", f"cam{i+1}_framing", row, FRAMING_OPTIONS); row += 1
            add_combo(f"cam{i+1}_yaw", f"cam{i+1}_yaw", row, YAW_OPTIONS); row += 1
        # Keep posture as a normal dropdown, but put enough distance between
        # it and the one-person checkbox to avoid accidental overlap/clicks on
        # small or highly-scaled displays.
        add_combo("posture", "posture", row, POSTURE_OPTIONS); row += 1
        add_combo("quality", "quality", row, QUALITY_OPTIONS); row += 1
        try:
            gl.setRowMinimumHeight(row, int(round(clamp(18 * self.ui_scale, 14, 34))))
        except Exception:
            pass
        row += 1
        self.chk_one_person = QCheckBox("One person throughout this clip")
        self.chk_one_person.setChecked(True)
        self.chk_one_person.toggled.connect(self._one_person_toggled)
        gl.addWidget(self.chk_one_person, row, 0, 1, 2); row += 1
        add_combo("num_persons", "num_persons", row, NUM_PERSONS_OPTIONS); row += 1
        add_combo("multi_person", "multi_person", row, MULTI_PERSON_OPTIONS); row += 1
        add_entry("start_sec", "start_sec", row, True); row += 1
        add_entry("end_sec", "end_sec", row, True); row += 1

        for i in range(3):
            defaults = infer_camera_defaults(i, "")
            self._set_combo(f"cam{i+1}_device", defaults["device"])
            self._set_combo(f"cam{i+1}_framing", defaults["framing"])
        self._set_combo("posture", "normal")
        self._set_combo("quality", "valid")
        self._set_combo("num_persons", "1")
        self._set_combo("multi_person", "no")
        self.fields["num_persons"].currentTextChanged.connect(self._num_persons_changed)
        try:
            self.fields["posture"].currentTextChanged.connect(self._posture_changed_update_suggested_csv_path)
        except Exception:
            pass

        help_grp = QGroupBox("Shortcuts / Workflow")
        hv = QVBoxLayout(help_grp)
        hv.addWidget(QLabel(
            "A/D: frame, Z/C: 1 sec, Shift+Z/C: 5 sec\n"
            "Q/E: mark start/end, Ctrl+S: save\n"
            "Enter Sync: capture sync_start for all videos\n"
            "After typing metadata, press Enter to return to shortcuts\n"
            "Per-cam metadata: device/framing/yaw are saved per camera row\n"
            "CSV file is created only by Save / Ctrl+S\n"
            "CSV folder follows source video folder fhp/nhp, not posture dropdown\n"
            "Saved row fix: double-click CSV cell to edit; or Apply Metadata / Delete Rows"
        ))
        form.addWidget(help_grp)
        self.saved_label = QLabel("Saved clips: 0")
        form.addWidget(self.saved_label)
        form.addStretch()

        self.save_log_preview = ActualCsvPreviewPanel(self, central)
        root.addWidget(self.save_log_preview)

    def _bind_shortcuts(self):
        shortcuts = [
            ("1", lambda: self.select_cam(0)),
            ("2", lambda: self.select_cam(1)),
            ("3", lambda: self.select_cam(2)),
            ("A", lambda: self.step_frame(-1)),
            ("D", lambda: self.step_frame(1)),
            ("Z", lambda: self.jump_seconds(-1)),
            ("C", lambda: self.jump_seconds(1)),
            ("Shift+Z", lambda: self.jump_seconds(-5)),
            ("Shift+C", lambda: self.jump_seconds(5)),
            ("Space", self.toggle_play),
            ("Q", self.set_annotation_start),
            ("E", self.set_annotation_end),
            ("R", self.reset_active_sync),
            ("Ctrl+R", self.reset_all_sync),
            ("Ctrl+S", self.save_annotation),
            ("Escape", self.close),
        ]
        for key, fn in shortcuts:
            QShortcut(QKeySequence(key), self).activated.connect(fn)

    def _focus_navigation_mode(self):
        """Return keyboard focus to the main annotation window.

        This prevents A/D/Z/C/Q/E from being typed into session_id/actor_id
        after the user has finished editing metadata or after saving rows.
        """
        try:
            fw = QApplication.focusWidget()
            if fw is not None and isinstance(fw, (QLineEdit, QComboBox)):
                fw.clearFocus()
        except Exception:
            pass
        try:
            if getattr(self, "preview_labels", None):
                self.preview_labels[self.active_cam].setFocus()
        except Exception:
            pass
        try:
            self.setFocus()
        except Exception:
            pass

    def _focus_navigation_mode_later(self):
        try:
            QTimer.singleShot(0, self._focus_navigation_mode)
        except Exception:
            self._focus_navigation_mode()

    # --------------------------------------------------------
    # Field helpers
    # --------------------------------------------------------
    def _set_combo(self, key, value):
        w = self.fields[key]
        if isinstance(w, QComboBox):
            idx = w.findText(str(value))
            if idx >= 0:
                w.setCurrentIndex(idx)
        elif isinstance(w, SegmentedChoice):
            w.set_value(value)

    def _get_field(self, key) -> str:
        w = self.fields[key]
        if isinstance(w, QComboBox):
            return w.currentText()
        if isinstance(w, SegmentedChoice):
            return w.currentText()
        return w.text()

    def _set_field(self, key, value):
        w = self.fields[key]
        if isinstance(w, QComboBox):
            idx = w.findText(str(value))
            if idx >= 0:
                w.setCurrentIndex(idx)
        elif isinstance(w, SegmentedChoice):
            w.set_value(value)
        else:
            w.setText(str(value))

    def _mark_required_field(self, key: str, missing: bool) -> None:
        w = self.fields.get(key)
        if w is None:
            return
        try:
            w.setProperty("missingRequired", "true" if missing else "false")
            w.style().unpolish(w)
            w.style().polish(w)
            w.update()
        except Exception:
            pass

    def _validate_required_metadata(self) -> bool:
        required = [("session_id", "session_id / action id (e.g., act01)"), ("actor_id", "actor_id / subject id (e.g., S01)")]
        missing = []
        for key, label in required:
            is_missing = not self._get_field(key).strip()
            self._mark_required_field(key, is_missing)
            if is_missing:
                missing.append((key, label))
        if missing:
            names = ", ".join(label for _, label in missing)
            QMessageBox.warning(
                self,
                "Required metadata missing",
                f"Please fill required field(s) before saving: {names}.",
            )
            try:
                self.fields[missing[0][0]].setFocus()
            except Exception:
                pass
            return False
        return True

    # --------------------------------------------------------
    # Remembered folders
    # --------------------------------------------------------
    def _remember_dir(self, key: str, path_like: str) -> None:
        directory = existing_dir_or_default(path_like)
        if not directory:
            return
        if key == "last_video_dir":
            self.last_video_dir = directory
        elif key == "last_csv_dir":
            self.last_csv_dir = directory
        self.app_settings[key] = directory
        save_app_settings(self.app_settings)
        print(f"[settings] {key} = {directory}")

    def _video_open_dir(self) -> str:
        return existing_dir_or_default(self.last_video_dir)

    def _csv_open_dir(self) -> str:
        # If a CSV path is already shown, use that first; otherwise use remembered CSV folder.
        current = self.edit_csv.text().strip() if hasattr(self, "edit_csv") else ""
        return existing_dir_or_default(current or self.last_csv_dir)

    # --------------------------------------------------------
    # Video-set metadata refresh
    # --------------------------------------------------------
    def _metadata_from_paths(self, paths: List[str]) -> Dict[str, str]:
        """Infer actor/action metadata from currently loaded or newly selected videos.

        v6.4 uses the same robust filename parser used during camera loading so
        ``S01_act03_yR0.mp4`` reliably becomes actor_id=S01, session_id=act03.
        This prevents a new action set from being suggested/saved as
        ``act03_Rset_multi_view.csv`` with the subject prefix missing.
        """
        valid = [p for p in paths if p]
        actor = ""
        session = ""
        for p in valid:
            try:
                meta = parse_metadata_from_filename(p)
            except Exception:
                meta = {}
            if not actor and meta.get("actor_id"):
                actor = normalize_actor_id(meta.get("actor_id", ""))
            if not session and meta.get("session_id"):
                session = normalize_session_id(meta.get("session_id", ""))
            if actor and session:
                break
        if not actor:
            actor = normalize_actor_id(_extract_subject_id_from_paths(valid))
        if not session:
            session = normalize_session_id(_extract_action_id_from_paths(valid))
        return {"actor_id": actor, "session_id": session}

    def _refresh_actor_action_from_paths(self, paths: List[str], force: bool = True) -> bool:
        """Update actor_id/session_id fields from video filenames.

        If force=True, explicit metadata in the loaded video names wins over
        whatever was left in the UI from the previous action. This is the desired
        dataset workflow: loading S01_act02_* should immediately switch the CSV
        target from S01_act01_* to S01_act02_*.
        """
        meta = self._metadata_from_paths(paths)
        changed = False
        actor = meta.get("actor_id", "")
        session = meta.get("session_id", "")
        if actor and (force or not self._get_field("actor_id")):
            if self._get_field("actor_id") != actor:
                self._set_field("actor_id", actor)
                changed = True
        if session and session != "multiview" and (force or not self._get_field("session_id")):
            if self._get_field("session_id") != session:
                self._set_field("session_id", session)
                changed = True
        if changed:
            print(f"[metadata refresh] actor_id={self._get_field('actor_id')} | session_id={self._get_field('session_id')}")
        return changed

    def _refresh_suggested_csv_path(self, summary_prefix: str = "CSV target refreshed") -> str:
        """Recompute and display the automatic CSV target for the current video set."""
        suggested_csv = self._suggested_csv_path_for_current_state()
        self.csv_path_manually_selected = False
        self.edit_csv.setText(suggested_csv)
        self._remember_dir("last_csv_dir", suggested_csv)
        if os.path.exists(suggested_csv):
            self._refresh_full_csv_preview_from_disk(suggested_csv, summary_prefix=summary_prefix)
        else:
            try:
                self.save_log_preview.set_rows(
                    [],
                    [],
                    summary=f"CSV will be created on Save / Ctrl+S → {suggested_csv}",
                    csv_path="",
                )
            except Exception:
                pass
        return suggested_csv

    # --------------------------------------------------------
    # CSV path suggestion
    # --------------------------------------------------------
    def _suggested_csv_path_for_current_state(self) -> str:
        return default_csv_path(
            [c.path for c in self.cams],
            self._get_field("actor_id") if hasattr(self, "fields") else "",
            self._get_field("session_id") if hasattr(self, "fields") else "",
            self._get_field("posture") if hasattr(self, "fields") else "",
        )

    def _posture_changed_update_suggested_csv_path(self, *_args) -> None:
        """Refresh the displayed CSV target after posture changes.

        v6.1: In the normal nested dataset tree, the CSV target is based on the
        source video folder (`fhp`/`nhp`), so changing the posture dropdown should
        NOT split one clip's timeline across different CSV files. This method is
        kept to refresh the preview/fallback path, but the route stays stable
        when source folders are available.
        """
        if getattr(self, "csv_path_manually_selected", False):
            return
        try:
            if not any(c.path for c in self.cams):
                return
            suggested_csv = self._suggested_csv_path_for_current_state()
            self.edit_csv.setText(suggested_csv)
            self._remember_dir("last_csv_dir", suggested_csv)
            if os.path.exists(suggested_csv):
                self._refresh_full_csv_preview_from_disk(suggested_csv, summary_prefix="Loaded existing CSV")
            else:
                self.save_log_preview.set_rows(
                    [],
                    [],
                    summary=(
                        f"CSV will be created on Save / Ctrl+S → {suggested_csv} "
                        f"[source folder route: annotations/{annotation_subdir_from_source_or_posture([c.path for c in self.cams], self._get_field('posture'))}/]"
                    ),
                    csv_path="",
                )
        except Exception as exc:
            print(f"[posture csv path update skipped] {exc}")

    # --------------------------------------------------------
    # File handling
    # --------------------------------------------------------
    def choose_csv(self):
        path = choose_save_file(
            self,
            "Choose annotation CSV path",
            self._csv_open_dir(),
            "CSV files (*.csv);;All files (*.*)",
            default_suffix="csv",
        )
        if path:
            # v4.4: choosing a CSV path must not create or touch the file.
            # The actual CSV file is created only when Save / Ctrl+S is pressed.
            self.csv_path_manually_selected = True
            self._remember_dir("last_csv_dir", path)
            self.edit_csv.setText(path)
            if os.path.exists(path):
                self._refresh_full_csv_preview_from_disk(path, summary_prefix="Loaded existing CSV")
            else:
                try:
                    self.save_log_preview.set_rows(
                        [],
                        [],
                        summary=f"CSV path selected, but file does not exist yet. Press Save / Ctrl+S to create → {os.path.basename(path)}",
                        csv_path="",
                    )
                except Exception:
                    pass

    def open_three_videos(self):
        paths = choose_open_files(
            self,
            "Open 3 videos",
            self._video_open_dir(),
            "Video files (*.mp4 *.mov *.avi *.mkv *.m4v);;All files (*.*)",
        )
        if not paths:
            return
        selected = paths[:3]
        for p in selected:
            self._remember_dir("last_video_dir", p)
        for i, p in enumerate(selected):
            self._load_cam(i, p, refresh_metadata=False)

        # v6.4: a newly opened 3-video set should define the actor/action.
        # Do not keep stale act01 metadata when the selected filenames are act02.
        self._refresh_actor_action_from_paths(selected, force=True)
        self._refresh_suggested_csv_path(summary_prefix="Loaded existing CSV for current video set")
        self.select_cam(0)
        self._update_all_status()

    def open_single_video(self, idx: int):
        self.select_cam(idx)
        path = choose_open_file(
            self,
            f"Open Cam {idx + 1} video",
            self._video_open_dir(),
            "Video files (*.mp4 *.mov *.avi *.mkv *.m4v);;All files (*.*)",
        )
        if path:
            self._remember_dir("last_video_dir", path)
            self._load_cam(idx, path, refresh_metadata=True)
            # v6.3: replacing any camera with Sxx_actYY_* switches the current
            # video set metadata and CSV target to that new action. Sync is reset
            # automatically, so accidental mixed-set saving is prevented.
            self._refresh_suggested_csv_path(summary_prefix="Loaded existing CSV for current video set")
            self._update_all_status()

    def _load_cam(self, idx: int, path: str, refresh_metadata: bool = True):
        old = self.cams[idx]
        cap = open_video_capture(path)
        if not cap.isOpened():
            QMessageBox.critical(self, "Error", f"Cannot open Cam {idx + 1}:\n{path}")
            return

        # v4.3: loading/replacing any camera means we are moving to a new
        # action/video set. Old sync offsets are no longer valid, so return to
        # clean LOCAL MODE automatically. The user should align the new videos
        # and press Enter Sync again.
        self._clear_sync_state_for_new_video_set(
            reason=f"new video loaded for Cam {idx + 1}: {os.path.basename(path)}",
            update_ui=False,
        )

        if old.cap is not None:
            old.cap.release()
        fps = safe_fps(cap.get(cv2.CAP_PROP_FPS), 30.0)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        meta = parse_metadata_from_filename(path)
        self.cams[idx] = CamState(path=path, fps=fps, total_frames=max(1, total), width=w, height=h, cap=cap, yaw_label=meta.get("yaw_label", ""))
        self._set_field(f"cam{idx+1}_yaw", self.cams[idx].yaw_label)

        # v4.2: infer per-camera device/framing defaults from view/yaw, while
        # still allowing the user to manually override them in the right panel.
        defaults = infer_camera_defaults(idx, self.cams[idx].yaw_label)
        self._set_field(f"cam{idx+1}_device", defaults["device"])
        self._set_field(f"cam{idx+1}_framing", meta.get("framing") or defaults["framing"])

        # v6.4: when a new action video is loaded, metadata from the filename
        # should replace the previous action's values. Otherwise act02 videos can
        # keep saving into the stale act01 CSV. open_three_videos() refreshes once
        # after all three files are loaded; open_single_video() refreshes here.
        if refresh_metadata:
            self._refresh_actor_action_from_paths([path], force=True)
        self.show_frame(idx, 0)

    # --------------------------------------------------------
    # Selection and display
    # --------------------------------------------------------
    def select_cam(self, idx: int):
        self.active_cam = idx
        for i, lbl in enumerate(self.preview_labels):
            lbl.setObjectName("preview_active" if i == idx else "preview")
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)
        self._sync_slider_to_current()
        self._update_status()

    def show_frame(self, idx: int, frame_idx: int):
        cam = self.cams[idx]
        if not cam.loaded():
            return
        frame_idx = max(0, min(int(frame_idx), cam.total_frames - 1))
        cam.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, bgr = cam.cap.read()
        if not ok or bgr is None:
            return
        cam.current_frame = frame_idx
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QIMAGE_FORMAT_RGB888)
        pix = QPixmap.fromImage(qimg)
        label = self.preview_labels[idx]
        lw = max(1, label.width())
        lh = max(1, label.height())
        scaled = pix.scaled(lw, lh, QT_KEEP_ASPECT_RATIO, QT_SMOOTH_TRANSFORMATION)
        label.setPixmap(scaled)
        # Prevent QLabel from changing its size hint to the pixmap size.
        label.setMinimumSize(1, 1)
        label.setSizePolicy(SP_IGNORED, SP_IGNORED)
        self.local_frame_edits[idx].setText(f"local frame: {frame_idx}")
        if idx == self.active_cam and not self.synced_mode:
            self._sync_slider_to_current()
        self._update_title(idx)

    def _update_title(self, idx: int):
        cam = self.cams[idx]
        if not cam.loaded():
            txt = f"▶ Cam {idx + 1} - not loaded" if idx == self.active_cam else f"Cam {idx + 1} - not loaded"
        else:
            name = os.path.basename(cam.path)
            s = "-" if cam.sync_start_frame is None else str(cam.sync_start_frame)
            e = "-" if cam.sync_end_frame is None else str(cam.sync_end_frame)
            prefix = "▶ " if idx == self.active_cam else ""
            txt = f"{prefix}Cam {idx + 1} | {name} | S:{s} E:{e}"
        self.title_labels[idx].setText(txt)

    def _update_all_status(self):
        for i in range(3):
            self._update_title(i)
        self._sync_slider_to_current()
        self._update_status()

    def _update_status(self):
        mode = "SYNC MODE" if self.synced_mode else "LOCAL MODE"
        active = self.active_cam + 1
        if self.synced_mode:
            txt = (f"{mode} | frame_offset: {self.global_offset} | "
                   f"time_offset: {self.global_offset_sec:.3f}s | "
                   f"annot_start: {self.annot_start_offset if self.annot_start_offset is not None else '-'} "
                   f"/ {self.annot_start_offset_sec if self.annot_start_offset_sec is not None else '-'} | "
                   f"annot_end: {self.annot_end_offset if self.annot_end_offset is not None else '-'} "
                   f"/ {self.annot_end_offset_sec if self.annot_end_offset_sec is not None else '-'}")
        else:
            cam = self.cams[self.active_cam]
            if cam.loaded():
                sec = frame_to_sec(cam.current_frame, cam.fps)
                txt = f"{mode} | Active Cam {active} | frame {cam.current_frame}/{cam.total_frames-1} | {sec:.2f}s ({sec_to_mmss(sec)})"
            else:
                txt = f"{mode} | Active Cam {active} | no video loaded"
        self.status_label.setText(txt)

    def _sync_slider_to_current(self):
        if self.synced_mode:
            starts = [c.sync_start_frame for c in self.cams if c.loaded() and c.sync_start_frame is not None]
            if not starts:
                self.slider.setMinimum(0); self.slider.setMaximum(1); self.slider.setValue(0); return
            min_back = -min(starts)
            max_forward = min((c.total_frames - 1 - c.sync_start_frame) for c in self.cams if c.loaded() and c.sync_start_frame is not None)
            self.slider.blockSignals(True)
            self.slider.setMinimum(min_back)
            self.slider.setMaximum(max_forward)
            self.slider.setValue(max(min_back, min(self.global_offset, max_forward)))
            self.slider.blockSignals(False)
        else:
            cam = self.cams[self.active_cam]
            self.slider.blockSignals(True)
            if cam.loaded():
                self.slider.setMinimum(0)
                self.slider.setMaximum(max(0, cam.total_frames - 1))
                self.slider.setValue(cam.current_frame)
            else:
                self.slider.setMinimum(0); self.slider.setMaximum(1); self.slider.setValue(0)
            self.slider.blockSignals(False)

    # --------------------------------------------------------
    # Navigation: LOCAL = active only, SYNC = all by same offset
    # --------------------------------------------------------
    def step_frame(self, delta: int):
        self.is_playing = False
        self.timer.stop()
        if self.synced_mode:
            if self.sync_by_time:
                # One frame step in synced mode is based on the active camera's frame interval,
                # then mapped to each camera using its own FPS.
                ref = self.cams[self.active_cam]
                ref_fps = ref.fps if ref.loaded() and ref.fps > 0 else 30.0
                print(f"[SYNC TIME] step all cams by active-frame time delta={delta/ref_fps:.6f}s")
                self.set_global_offset_sec(self.global_offset_sec + delta / ref_fps)
            else:
                print(f"[SYNC FRAME] step all cams by shared frame delta={delta}")
                self.set_global_offset(self.global_offset + delta)
        else:
            print(f"[LOCAL MODE] step ONLY Cam {self.active_cam + 1}, delta={delta}")
            cam = self.cams[self.active_cam]
            if cam.loaded():
                self.show_frame(self.active_cam, cam.current_frame + delta)
                self._update_status()

    def jump_seconds(self, sec: float):
        self.is_playing = False
        self.timer.stop()
        if self.synced_mode:
            if self.sync_by_time:
                print(f"[SYNC TIME] jump all cams by sec={sec}")
                self.set_global_offset_sec(self.global_offset_sec + sec)
            else:
                ref_fps = self.cams[self.active_cam].fps if self.cams[self.active_cam].loaded() else 30.0
                delta = int(round(sec * ref_fps))
                print(f"[SYNC FRAME] jump all cams by shared frame delta={delta}")
                self.set_global_offset(self.global_offset + delta)
        else:
            print(f"[LOCAL MODE] jump ONLY Cam {self.active_cam + 1}, sec={sec}")
            cam = self.cams[self.active_cam]
            if cam.loaded():
                self.show_frame(self.active_cam, cam.current_frame + int(round(sec * cam.fps)))
                self._update_status()

    def _synced_cams(self):
        return [c for c in self.cams if c.loaded() and c.sync_start_frame is not None]

    def set_global_offset(self, offset: int):
        synced_cams = self._synced_cams()
        if not synced_cams:
            return
        min_offset = max(-c.sync_start_frame for c in synced_cams)
        max_offset = min(c.total_frames - 1 - c.sync_start_frame for c in synced_cams)
        offset = max(min_offset, min(int(offset), max_offset))
        self.global_offset = offset
        # Keep time offset approximately consistent with active cam for UI display.
        ref = self.cams[self.active_cam]
        ref_fps = ref.fps if ref.loaded() and ref.fps > 0 else 30.0
        self.global_offset_sec = self.global_offset / ref_fps
        for i, cam in enumerate(self.cams):
            if cam.loaded() and cam.sync_start_frame is not None:
                self.show_frame(i, cam.sync_start_frame + self.global_offset)
        self._sync_slider_to_current()
        self._update_status()

    def set_global_offset_sec(self, offset_sec: float):
        synced_cams = self._synced_cams()
        if not synced_cams:
            return
        min_sec = max(-c.sync_start_frame / c.fps for c in synced_cams if c.fps > 0)
        max_sec = min((c.total_frames - 1 - c.sync_start_frame) / c.fps for c in synced_cams if c.fps > 0)
        offset_sec = max(min_sec, min(float(offset_sec), max_sec))
        self.global_offset_sec = offset_sec
        # Active frame offset is only for slider/status compatibility.
        ref = self.cams[self.active_cam]
        ref_fps = ref.fps if ref.loaded() and ref.fps > 0 else 30.0
        self.global_offset = int(round(offset_sec * ref_fps))
        for i, cam in enumerate(self.cams):
            if cam.loaded() and cam.sync_start_frame is not None:
                target = cam.sync_start_frame + int(round(offset_sec * cam.fps))
                self.show_frame(i, target)
        self._sync_slider_to_current()
        self._update_status()

    def toggle_sync_unit(self):
        # v3.7: the TIME/FRAME UI was removed to keep the workflow simple.
        # Internally we keep time-based sync, which is safer when cameras have
        # slightly different FPS values.
        self.sync_by_time = True
        print("Sync unit fixed: TIME")
        if self.synced_mode:
            self.set_global_offset_sec(self.global_offset_sec)

    def _slider_moved(self, value: int):
        if self.synced_mode:
            if self.sync_by_time:
                ref = self.cams[self.active_cam]
                ref_fps = ref.fps if ref.loaded() and ref.fps > 0 else 30.0
                self.global_offset_sec = value / ref_fps
                self.global_offset = value
            else:
                self.global_offset = value
            self._update_status()
        else:
            cam = self.cams[self.active_cam]
            if cam.loaded():
                self.local_frame_edits[self.active_cam].setText(f"local frame: {value}")

    def _slider_released(self):
        if self.synced_mode:
            if self.sync_by_time:
                ref = self.cams[self.active_cam]
                ref_fps = ref.fps if ref.loaded() and ref.fps > 0 else 30.0
                self.set_global_offset_sec(self.slider.value() / ref_fps)
            else:
                self.set_global_offset(self.slider.value())
        else:
            cam = self.cams[self.active_cam]
            if cam.loaded():
                self.show_frame(self.active_cam, self.slider.value())
                self._update_status()

    def toggle_play(self):
        if self.synced_mode:
            if not any(c.loaded() and c.sync_start_frame is not None for c in self.cams):
                return
        else:
            if not self.cams[self.active_cam].loaded():
                return
        self.is_playing = not self.is_playing
        if self.is_playing:
            fps = self.cams[self.active_cam].fps if self.cams[self.active_cam].loaded() else 30.0
            self.timer.start(max(1, int(1000 / max(1.0, fps))))
        else:
            self.timer.stop()

    def _play_step(self):
        if self.synced_mode:
            before = self.global_offset
            self.set_global_offset(self.global_offset + 1)
            if self.global_offset == before:
                self.timer.stop(); self.is_playing = False
        else:
            cam = self.cams[self.active_cam]
            if not cam.loaded() or cam.current_frame >= cam.total_frames - 1:
                self.timer.stop(); self.is_playing = False; return
            self.show_frame(self.active_cam, cam.current_frame + 1)
            self._update_status()

    # --------------------------------------------------------
    # Sync
    # --------------------------------------------------------
    def _clear_sync_state_for_new_video_set(self, reason: str = "", update_ui: bool = True):
        """Reset stale synchronization/annotation state when a new action/video set is loaded.

        Without this, replacing videos while still in SYNC MODE can leave old
        sync_start_frame/sync_end_frame values attached to the remaining camera
        states. Then Z/C/A/D may appear to stop working because the app is still
        trying to navigate by the previous multi-view sync offset. Loading a new
        clip/action should always return to clean LOCAL MODE; the user can then
        align frames and press Enter Sync again.
        """
        self.is_playing = False
        self.timer.stop()
        self.synced_mode = False
        self.global_offset = 0
        self.global_offset_sec = 0.0
        self.annot_start_offset = None
        self.annot_end_offset = None
        self.annot_start_offset_sec = None
        self.annot_end_offset_sec = None
        for cam in self.cams:
            cam.sync_start_frame = None
            cam.sync_end_frame = None
        if hasattr(self, "fields"):
            self._set_field("start_sec", "")
            self._set_field("end_sec", "")
        if reason:
            print(f"[AUTO RESET SYNC] {reason}")
        if update_ui:
            self._update_all_status()

    def _loaded_cam_indices(self) -> List[int]:
        return [i for i, c in enumerate(self.cams) if c.loaded()]

    def set_all_sync_start_from_current(self, show_message: bool = False) -> bool:
        """Capture sync-start for every loaded camera at its current frame."""
        loaded = self._loaded_cam_indices()
        if not loaded:
            if show_message:
                QMessageBox.warning(self, "Warning", "Open videos first.")
            return False
        for i in loaded:
            self.cams[i].sync_start_frame = int(self.cams[i].current_frame)
        summary = ", ".join(f"Cam {i + 1}=S:{self.cams[i].sync_start_frame}" for i in loaded)
        print(f"[SYNC START ALL] {summary}")
        self._update_all_status()
        return True

    def set_all_sync_end_from_current(self, show_message: bool = True) -> bool:
        """Capture sync-end for every loaded camera at its current frame."""
        loaded = self._loaded_cam_indices()
        if not loaded:
            if show_message:
                QMessageBox.warning(self, "Warning", "Open videos first.")
            return False
        for i in loaded:
            self.cams[i].sync_end_frame = int(self.cams[i].current_frame)
        summary = ", ".join(f"Cam {i + 1}=E:{self.cams[i].sync_end_frame}" for i in loaded)
        print(f"[SYNC END ALL] {summary}")
        self._update_all_status()
        return True

    def set_all_sync_end_from_annotation_end(self, show_message: bool = False) -> bool:
        """Capture sync_end_frame for all loaded cameras using the current annotation end.

        This is the v3.2 default workflow. The user presses Enter Sync once to
        define the synchronized zero point, navigates to the clip end, then
        presses E. At that moment this method stores each camera's actual local
        end frame, so the CSV column sync_end_frame is not blank.
        """
        loaded = self._loaded_cam_indices()
        if not loaded:
            if show_message:
                QMessageBox.warning(self, "Warning", "Open videos first.")
            return False
        if not self.synced_mode:
            if show_message:
                QMessageBox.warning(self, "Warning", "Enter Synced Annot Mode first.")
            return False
        for i in loaded:
            cam = self.cams[i]
            if cam.sync_start_frame is None:
                continue
            if self.sync_by_time:
                offset_sec = self.global_offset_sec
                frame = cam.sync_start_frame + int(round(offset_sec * cam.fps))
            else:
                frame = cam.sync_start_frame + int(self.global_offset)
            frame = max(0, min(int(frame), cam.total_frames - 1))
            cam.sync_end_frame = frame
        summary = ", ".join(
            f"Cam {i + 1}=E:{self.cams[i].sync_end_frame}"
            for i in loaded if self.cams[i].sync_end_frame is not None
        )
        print(f"[SYNC END ALL FROM E] {summary}")
        self._update_all_status()
        return True

    def set_sync_start(self, idx: int):
        # Kept for compatibility, but the UI now uses all-camera sync capture.
        self.select_cam(idx)
        cam = self.cams[idx]
        if not cam.loaded():
            return
        cam.sync_start_frame = cam.current_frame
        print(f"Cam {idx + 1} Start Sync = {cam.sync_start_frame}")
        self._update_all_status()

    def set_sync_end(self, idx: int):
        # Kept for compatibility, but the UI now uses all-camera sync capture.
        self.select_cam(idx)
        cam = self.cams[idx]
        if not cam.loaded():
            return
        cam.sync_end_frame = cam.current_frame
        print(f"Cam {idx + 1} End Sync = {cam.sync_end_frame}")
        self._update_all_status()

    def enter_synced_mode(self):
        loaded = self._loaded_cam_indices()
        if not loaded:
            QMessageBox.warning(self, "Warning", "Open videos first.")
            return

        # New workflow: after the user aligns the three videos locally, pressing
        # Enter Sync automatically records the current frame of each loaded camera
        # as its sync-start frame. No separate per-camera Sync S clicks needed.
        self.set_all_sync_start_from_current(show_message=False)

        self.synced_mode = True
        self.is_playing = False
        self.timer.stop()
        self.global_offset = 0
        self.global_offset_sec = 0.0
        self.annot_start_offset = None
        self.annot_end_offset = None
        self.annot_start_offset_sec = None
        self.annot_end_offset_sec = None
        self._set_field("start_sec", "")
        self._set_field("end_sec", "")
        print("[ENTER SYNC MODE] auto-captured sync_start for loaded cams; offset=0")
        if self.sync_by_time:
            self.set_global_offset_sec(0.0)
        else:
            self.set_global_offset(0)

    def exit_synced_mode(self):
        self.synced_mode = False
        self.is_playing = False
        self.timer.stop()
        self._sync_slider_to_current()
        self._update_status()
        print("[EXIT SYNC MODE] back to local mode")

    def reset_active_sync(self):
        cam = self.cams[self.active_cam]
        cam.sync_start_frame = None
        cam.sync_end_frame = None
        self.synced_mode = False
        self.annot_start_offset = None
        self.annot_end_offset = None
        self._set_field("start_sec", "")
        self._set_field("end_sec", "")
        self._update_all_status()
        print(f"Reset sync for Cam {self.active_cam + 1}")

    def reset_all_sync(self):
        for cam in self.cams:
            cam.sync_start_frame = None
            cam.sync_end_frame = None
        self.synced_mode = False
        self.global_offset = 0
        self.global_offset_sec = 0.0
        self.annot_start_offset = None
        self.annot_end_offset = None
        self.annot_start_offset_sec = None
        self.annot_end_offset_sec = None
        self._set_field("start_sec", "")
        self._set_field("end_sec", "")
        self._update_all_status()
        print("Reset all sync")

    # --------------------------------------------------------
    # Annotation
    # --------------------------------------------------------
    def set_annotation_start(self):
        if not self.synced_mode:
            QMessageBox.warning(self, "Warning", "Enter Synced Annot Mode first.")
            return
        self.annot_start_offset = self.global_offset
        self.annot_start_offset_sec = self.global_offset_sec
        active = self.cams[self.active_cam]
        if self.sync_by_time:
            start_frame = active.sync_start_frame + int(round(self.annot_start_offset_sec * active.fps)) if active.sync_start_frame is not None else 0
            start_sec = frame_to_sec(start_frame, active.fps)
            self._set_field("start_sec", f"time_offset {self.annot_start_offset_sec:.3f}s / active {start_sec:.2f}s")
        else:
            start_sec = frame_to_sec(active.sync_start_frame + self.annot_start_offset, active.fps) if active.sync_start_frame is not None else 0
            self._set_field("start_sec", f"frame_offset {self.annot_start_offset} / active {start_sec:.2f}s")
        self._update_status()

    def set_annotation_end(self):
        if not self.synced_mode:
            QMessageBox.warning(self, "Warning", "Enter Synced Annot Mode first.")
            return
        self.annot_end_offset = self.global_offset
        self.annot_end_offset_sec = self.global_offset_sec
        active = self.cams[self.active_cam]
        if self.sync_by_time:
            end_frame = active.sync_start_frame + int(round(self.annot_end_offset_sec * active.fps)) if active.sync_start_frame is not None else 0
            end_sec = frame_to_sec(end_frame, active.fps)
            self._set_field("end_sec", f"time_offset {self.annot_end_offset_sec:.3f}s / active {end_sec:.2f}s")
        else:
            end_sec = frame_to_sec(active.sync_start_frame + self.annot_end_offset, active.fps) if active.sync_start_frame is not None else 0
            self._set_field("end_sec", f"frame_offset {self.annot_end_offset} / active {end_sec:.2f}s")
        # v3.2: pressing E also records sync_end_frame for all loaded cameras.
        # This removes the need for per-camera Sync E clicks.
        self.set_all_sync_end_from_annotation_end(show_message=False)
        self._update_status()

    def _update_save_log_preview(self, csv_path: str, rows: List[Dict[str, object]]):
        # v4.1: CSV files are cumulative per subject/action. After appending
        # a new annotation interval, show the ENTIRE actual CSV file in the
        # bottom table so normal/FHP/etc. segments stay visible together.
        total_rows = actual_csv_data_row_count(csv_path)
        shown_n = max(1, total_rows)

        appended_text = read_actual_csv_tail_text(csv_path, data_rows=len(rows), include_header=True)
        full_text = read_actual_csv_tail_text(csv_path, data_rows=shown_n, include_header=True)
        appended_header, appended_rows = read_actual_csv_tail_rows(csv_path, data_rows=len(rows))
        full_header, full_rows = read_actual_csv_tail_rows(csv_path, data_rows=shown_n)
        stats = read_actual_csv_stats(csv_path)
        summary = compact_saved_rows_preview(rows)

        self.last_save_csv_path = csv_path
        self.last_actual_appended_text = appended_text
        self.last_actual_csv_tail_text = full_text
        self.last_actual_appended_header = appended_header
        self.last_actual_appended_rows = appended_rows
        self.last_actual_tail_header = full_header
        self.last_actual_tail_rows = full_rows
        self.last_preview_row_count = len(full_rows)
        self.last_preview_start_data_index = 0
        self.last_save_log_summary = (
            f"Appended {len(rows)} rows → {os.path.basename(csv_path)} | {stats} | "
            f"showing ALL rows in this CSV | latest: {summary}"
        )
        self.last_save_log_text = (
            f"CSV path: {csv_path}\n"
            f"{stats}\n\n"
            "[Latest appended rows - READ BACK FROM ACTUAL CSV FILE]\n"
            f"{appended_text}\n\n"
            "[Entire CSV for this subject/action - READ BACK FROM ACTUAL CSV FILE]\n"
            f"{full_text}"
        )

        try:
            self.save_log_preview.set_rows(
                full_header,
                full_rows,
                summary=f"Cumulative CSV view | {self.last_save_log_summary}",
                csv_path=csv_path,
            )
        except Exception as exc:
            print(f"[csv preview table error] {exc}")

    def _selected_preview_data_indices(self, default_all: bool = True) -> List[int]:
        """Map selected preview-table rows to actual CSV data row indices.

        Indices are zero-based over data rows, excluding the CSV header. If no
        row is selected and default_all=True, all rows currently shown in the
        bottom preview are targeted. This makes the common correction workflow
        quick: change posture/quality on the right, then press Apply Metadata.
        """
        try:
            table = self.save_log_preview.table
        except Exception:
            return []
        row_nums = set()
        try:
            for item in table.selectedIndexes():
                row_nums.add(int(item.row()))
        except Exception:
            pass
        if not row_nums and default_all:
            try:
                row_nums = set(range(table.rowCount()))
            except Exception:
                row_nums = set()
        start = int(getattr(self, "last_preview_start_data_index", 0) or 0)
        return sorted({start + r for r in row_nums})

    def _refresh_full_csv_preview_from_disk(self, csv_path: str, summary_prefix: str = "Full CSV preview"):
        """Show every saved row in the current subject/action CSV.

        v4.1 behavior: one subject/action multi-view CSV is cumulative.
        Multiple labeled intervals, such as normal and FHP segments from the
        same synchronized video set, should all be visible together in the
        bottom table.
        """
        if not csv_path or not os.path.exists(csv_path):
            return
        try:
            total_rows = actual_csv_data_row_count(csv_path)
        except Exception:
            total_rows = 0
        # Use at least 1 so the header/empty file state is still refreshed.
        self._refresh_actual_csv_preview_from_disk(
            csv_path,
            data_rows=max(1, total_rows),
            summary_prefix=summary_prefix,
        )

    def _refresh_actual_csv_preview_from_disk(self, csv_path: str, data_rows: Optional[int] = None, summary_prefix: str = "Actual CSV preview"):
        if not csv_path or not os.path.exists(csv_path):
            return
        n = int(data_rows or max(12, int(getattr(self, "last_preview_row_count", 0) or 0), 3))
        header, rows = read_actual_csv_tail_rows(csv_path, data_rows=n)
        total_rows = actual_csv_data_row_count(csv_path)
        self.last_save_csv_path = csv_path
        self.last_actual_appended_header = header
        self.last_actual_appended_rows = rows
        self.last_actual_tail_header = header
        self.last_actual_tail_rows = rows
        self.last_preview_row_count = len(rows)
        self.last_preview_start_data_index = max(0, total_rows - len(rows))
        stats = read_actual_csv_stats(csv_path)
        tail_text = read_actual_csv_tail_text(csv_path, data_rows=n, include_header=True)
        self.last_actual_appended_text = tail_text
        self.last_actual_csv_tail_text = tail_text
        self.last_save_log_summary = f"{summary_prefix} → {os.path.basename(csv_path)} | {stats}"
        self.last_save_log_text = (
            f"CSV path: {csv_path}\n"
            f"{stats}\n\n"
            "[CSV file tail - READ BACK FROM ACTUAL CSV FILE]\n"
            f"{tail_text}"
        )
        try:
            self.save_log_preview.set_rows(
                header,
                rows,
                summary=f"{self.last_save_log_summary} | select rows then Apply Metadata/Delete Rows; no selection = all shown rows",
                csv_path=csv_path,
            )
        except Exception as exc:
            print(f"[csv preview refresh error] {exc}")

    def _current_metadata_updates_for_row(self, existing_row, header) -> Dict[str, str]:
        updates = {
            "session_id": self._get_field("session_id"),
            "actor_id": self._get_field("actor_id"),
            "posture": self._get_field("posture"),
            "quality": self._get_field("quality"),
            "num_persons": self._get_field("num_persons"),
            "multi_person": self._get_field("multi_person"),
        }
        cam_idx = _csv_row_get(existing_row, header, "camera_index").strip()
        if cam_idx in {"1", "2", "3"}:
            updates["camera_device"] = self._get_field(f"cam{cam_idx}_device")
            updates["framing"] = self._get_field(f"cam{cam_idx}_framing")
            yaw = self._get_field(f"cam{cam_idx}_yaw")
            if yaw:
                view_set = _infer_view_set_from_paths([getattr(self, "last_save_csv_path", "") or self.edit_csv.text().strip()])
                if not view_set:
                    view_set = _infer_view_set_from_yaw_labels([self._get_field(f"cam{i+1}_yaw") for i in range(len(self.cams))])
                updates["yaw_label"] = make_annotation_yaw_label(yaw, view_set)
        return updates

    def handle_csv_preview_item_changed(self, item):
        """Write an edited bottom-preview cell back to the actual CSV file.

        This enables the Excel-like correction workflow: double-click a cell in
        the bottom CSV preview, edit the value, press Enter, and the real CSV
        file is rewritten immediately with a timestamped backup.
        """
        try:
            if getattr(self.save_log_preview, "_updating_table", False):
                return
        except Exception:
            pass
        if item is None:
            return
        csv_path = (getattr(self, "last_save_csv_path", "") or self.edit_csv.text().strip())
        if not csv_path or not os.path.exists(csv_path):
            return
        try:
            preview_row = int(item.row())
            col_idx = int(item.column())
        except Exception:
            return
        data_idx = int(getattr(self, "last_preview_start_data_index", 0) or 0) + preview_row
        header, csv_rows = read_actual_csv_all_rows(csv_path)
        if not header or not (0 <= data_idx < len(csv_rows)) or not (0 <= col_idx < len(header)):
            return
        row = list(csv_rows[data_idx])
        while len(row) < len(header):
            row.append("")
        old_value = str(row[col_idx])
        new_value = str(item.text())
        if new_value == old_value:
            return
        row[col_idx] = new_value
        csv_rows[data_idx] = row
        col_name = str(header[col_idx])
        try:
            write_actual_csv_all_rows(csv_path, header, csv_rows, make_backup=True)
        except Exception as exc:
            QMessageBox.critical(self, "CSV cell edit failed", f"Could not write the edited cell to CSV:\n{csv_path}\n\n{exc}")
            try:
                item.setText(old_value)
            except Exception:
                pass
            return
        try:
            shown_n = max(1, int(getattr(self, "last_preview_row_count", 0) or 1))
            self._refresh_actual_csv_preview_from_disk(
                csv_path,
                data_rows=shown_n,
                summary_prefix=f"Edited cell {col_name} row {data_idx + 1}",
            )
            # Restore a visible current cell after refresh when possible.
            try:
                self.save_log_preview.table.setCurrentCell(preview_row, col_idx)
            except Exception:
                pass
        except Exception as exc:
            print(f"[CSV inline edit refresh warning] {exc}")
        self._focus_navigation_mode_later()

    def apply_current_metadata_to_selected_csv_rows(self):
        csv_path = (getattr(self, "last_save_csv_path", "") or self.edit_csv.text().strip())
        if not csv_path or not os.path.exists(csv_path):
            QMessageBox.warning(self, "No CSV", "No actual CSV file is available to edit yet.")
            return
        if not self._validate_required_metadata():
            return
        header, csv_rows = read_actual_csv_all_rows(csv_path)
        if not header:
            QMessageBox.warning(self, "No CSV rows", "The CSV file is empty or could not be read.")
            return
        target_indices = self._selected_preview_data_indices(default_all=True)
        target_indices = [i for i in target_indices if 0 <= i < len(csv_rows)]
        if not target_indices:
            QMessageBox.warning(self, "No rows selected", "Select CSV rows in the bottom table, or leave nothing selected to update all shown rows.")
            return
        try:
            for data_idx in target_indices:
                row = list(csv_rows[data_idx])
                while len(row) < len(header):
                    row.append("")
                for col, value in self._current_metadata_updates_for_row(row, header).items():
                    row = _csv_row_set(row, header, col, value)
                csv_rows[data_idx] = row
            write_actual_csv_all_rows(csv_path, header, csv_rows, make_backup=True)
        except Exception as exc:
            QMessageBox.critical(self, "CSV edit failed", f"Could not update CSV rows:\n{csv_path}\n\n{exc}")
            return
        self._refresh_actual_csv_preview_from_disk(csv_path, data_rows=max(len(target_indices), int(getattr(self, "last_preview_row_count", 0) or 3)), summary_prefix=f"Updated {len(target_indices)} row(s)")
        self._focus_navigation_mode_later()
        try:
            self.status_label.setText(f"Updated {len(target_indices)} CSV row(s). Backup created next to the CSV.")
        except Exception:
            pass

    def delete_selected_csv_rows(self):
        csv_path = (getattr(self, "last_save_csv_path", "") or self.edit_csv.text().strip())
        if not csv_path or not os.path.exists(csv_path):
            QMessageBox.warning(self, "No CSV", "No actual CSV file is available to edit yet.")
            return
        header, csv_rows = read_actual_csv_all_rows(csv_path)
        if not header:
            QMessageBox.warning(self, "No CSV rows", "The CSV file is empty or could not be read.")
            return
        target_indices = self._selected_preview_data_indices(default_all=True)
        target_indices = sorted({i for i in target_indices if 0 <= i < len(csv_rows)}, reverse=True)
        if not target_indices:
            QMessageBox.warning(self, "No rows selected", "Select CSV rows in the bottom table, or leave nothing selected to delete all shown rows.")
            return
        msg = (
            f"Delete {len(target_indices)} row(s) from the actual CSV file?\n\n"
            f"{csv_path}\n\n"
            "A timestamped backup will be created first."
        )
        try:
            ret = QMessageBox.question(self, "Delete CSV rows", msg)
            yes_value = getattr(QMessageBox, "Yes", None)
            if yes_value is None:
                yes_value = getattr(getattr(QMessageBox, "StandardButton", object), "Yes", None)
            if yes_value is not None and ret != yes_value:
                return
        except Exception:
            pass
        try:
            for data_idx in target_indices:
                del csv_rows[data_idx]
            write_actual_csv_all_rows(csv_path, header, csv_rows, make_backup=True)
        except Exception as exc:
            QMessageBox.critical(self, "CSV delete failed", f"Could not delete CSV rows:\n{csv_path}\n\n{exc}")
            return
        self._refresh_actual_csv_preview_from_disk(csv_path, data_rows=12, summary_prefix=f"Deleted {len(target_indices)} row(s)")
        self._focus_navigation_mode_later()
        try:
            self.status_label.setText(f"Deleted {len(target_indices)} CSV row(s). Backup created next to the CSV.")
        except Exception:
            pass

    def show_save_log_dialog(self):
        if not self.last_save_log_text:
            QMessageBox.information(self, "Actual CSV View", "No saved rows yet. Press Save / Ctrl+S after setting an annotation range.")
            return
        try:
            self._raw_csv_viewer_window = RawCsvViewerWindow(
                "Actual CSV Saved Rows / File Tail",
                self.last_save_log_summary,
                getattr(self, "last_actual_appended_header", []),
                getattr(self, "last_actual_appended_rows", []),
                getattr(self, "last_actual_tail_header", []),
                getattr(self, "last_actual_tail_rows", []),
                self.last_save_log_text,
                self,
            )
            self._raw_csv_viewer_window.show()
            self._raw_csv_viewer_window.raise_()
            self._raw_csv_viewer_window.activateWindow()
        except Exception:
            msg = QMessageBox(self)
            msg.setWindowTitle("Actual CSV Saved Rows")
            msg.setText(self.last_save_log_summary)
            msg.setDetailedText(self.last_save_log_text)
            msg.exec() if hasattr(msg, "exec") else msg.exec_()

    def _append_rows_with_permission_recovery(self, csv_path: str, rows: List[Dict[str, object]]) -> Optional[str]:
        """Append rows, recovering from Windows/WSL permission problems.

        Returns the path that was actually written, or None if saving was cancelled/failed.
        """
        try:
            append_rows_to_csv(csv_path, rows)
            return csv_path
        except PermissionError as exc:
            print(f"[CSV PERMISSION DENIED] {csv_path}: {exc}")
            QMessageBox.warning(self, "CSV permission denied", permission_error_hint(csv_path, exc))

            # First let the user choose another path. If they cancel, write to a
            # guaranteed local fallback under the Linux/user home directory.
            suggested = local_fallback_csv_path(csv_path)
            alt_path = choose_save_file(
                self,
                "Choose another writable CSV",
                os.path.dirname(suggested),
                "CSV files (*.csv);;All files (*.*)",
                default_suffix="csv",
            )
            if not alt_path:
                alt_path = suggested

            try:
                append_rows_to_csv(alt_path, rows)
            except Exception as alt_exc:
                QMessageBox.critical(
                    self,
                    "CSV save failed",
                    f"Could not save to fallback/alternate CSV either:\n{alt_path}\n\n{alt_exc}",
                )
                return None

            self.csv_path_manually_selected = True
            self.edit_csv.setText(alt_path)
            self._remember_dir("last_csv_dir", alt_path)
            QMessageBox.information(
                self,
                "Saved to alternate CSV",
                f"The original CSV path was not writable.\nSaved rows to:\n{alt_path}",
            )
            return alt_path
        except OSError as exc:
            print(f"[CSV OS ERROR] {csv_path}: {exc}")
            QMessageBox.critical(self, "CSV save failed", f"Could not save CSV:\n{csv_path}\n\n{exc}")
            return None

    def save_annotation(self):
        if not self.synced_mode:
            QMessageBox.warning(self, "Warning", "Enter Synced Annot Mode first.")
            return
        if self.annot_start_offset is None or self.annot_end_offset is None:
            QMessageBox.warning(self, "Warning", "Set annotation Start(Q) and End(E) first.")
            return
        if self.sync_by_time:
            if self.annot_start_offset_sec is None or self.annot_end_offset_sec is None:
                QMessageBox.warning(self, "Warning", "Set annotation Start(Q) and End(E) first.")
                return
            if self.annot_end_offset_sec <= self.annot_start_offset_sec:
                QMessageBox.warning(self, "Warning", "End time offset must be greater than Start time offset.")
                return
        else:
            if self.annot_end_offset <= self.annot_start_offset:
                QMessageBox.warning(self, "Warning", "End offset must be greater than Start offset.")
                return
        # v6.4: just before saving, refresh actor/action from the loaded video
        # filenames one more time. This guarantees that a newly loaded act02 set
        # cannot be accidentally appended to the previous act01 CSV.
        self._refresh_actor_action_from_paths([c.path for c in self.cams if c.path], force=True)
        if not self._validate_required_metadata():
            return
        # v4.5: enforce the corrected semantics in the UI/CSV as well.
        # actor_id is the subject/person (S01), session_id is the action id (act01).
        self._set_field("actor_id", normalize_actor_id(self._get_field("actor_id")))
        self._set_field("session_id", normalize_session_id(self._get_field("session_id")))
        csv_path = self.edit_csv.text().strip()
        if (not csv_path) or (not getattr(self, "csv_path_manually_selected", False)):
            # v6.1: no Auto CSV file creation during loading. The suggested
            # path is recomputed here after required metadata is available.
            # The annotation folder follows the source video folder (fhp/nhp),
            # not the currently selected interval-level posture dropdown.
            csv_path = default_csv_path([c.path for c in self.cams], self._get_field("actor_id"), self._get_field("session_id"), self._get_field("posture"))
            self.edit_csv.setText(csv_path)
        if csv_path:
            self._remember_dir("last_csv_dir", csv_path)

        source_group = _infer_source_annotation_group_from_paths([c.path for c in self.cams])
        if source_group == "mixed":
            QMessageBox.warning(
                self,
                "Mixed source folders",
                "Loaded camera videos contain both fhp and nhp source folders.\n\n"
                "Use videos from one source group for a single synchronized set, "
                "or choose a CSV path manually."
            )
            return

        if self.chk_one_person.isChecked():
            self._set_combo("num_persons", "1")
            self._set_combo("multi_person", "no")

        rows = []
        current_view_set = _infer_view_set_from_paths([c.path for c in self.cams])
        if not current_view_set:
            current_view_set = _infer_view_set_from_yaw_labels([self._get_field(f"cam{i+1}_yaw") for i in range(len(self.cams))])
        for i, cam in enumerate(self.cams):
            if not cam.loaded() or cam.sync_start_frame is None:
                continue
            if self.sync_by_time:
                start_frame = cam.sync_start_frame + int(round(self.annot_start_offset_sec * cam.fps))
                end_frame = cam.sync_start_frame + int(round(self.annot_end_offset_sec * cam.fps))
            else:
                start_frame = cam.sync_start_frame + self.annot_start_offset
                end_frame = cam.sync_start_frame + self.annot_end_offset
            start_frame = max(0, min(start_frame, cam.total_frames - 1))
            end_frame = max(0, min(end_frame, cam.total_frames - 1))
            # Safety fallback: if sync_end_frame was not captured for any reason,
            # store the annotation end frame in sync_end_frame rather than writing blank.
            if cam.sync_end_frame is None:
                cam.sync_end_frame = int(end_frame)
            raw_yaw = self._get_field(f"cam{i+1}_yaw") or cam.yaw_label
            yaw = make_annotation_yaw_label(raw_yaw, current_view_set)
            row = {
                "video_id": os.path.basename(cam.path),
                "session_id": self._get_field("session_id"),
                "actor_id": self._get_field("actor_id"),
                "camera_device": self._get_field(f"cam{i+1}_device"),
                "camera_index": i + 1,
                "yaw_label": yaw,
                "framing": self._get_field(f"cam{i+1}_framing"),
                "posture": self._get_field("posture"),
                "quality": self._get_field("quality"),
                "num_persons": self._get_field("num_persons"),
                "multi_person": self._get_field("multi_person"),
                "fps": f"{cam.fps:.6f}",
                "resolution": f"{cam.width}x{cam.height}",
                "sync_start_frame": cam.sync_start_frame,
                "sync_end_frame": "" if cam.sync_end_frame is None else cam.sync_end_frame,
                "annot_start_offset": f"{self.annot_start_offset_sec:.6f}s" if self.sync_by_time else self.annot_start_offset,
                "annot_end_offset": f"{self.annot_end_offset_sec:.6f}s" if self.sync_by_time else self.annot_end_offset,
                "start_frame": start_frame,
                "end_frame": end_frame,
                "start_sec": f"{frame_to_sec(start_frame, cam.fps):.3f}",
                "end_sec": f"{frame_to_sec(end_frame, cam.fps):.3f}",
            }
            rows.append(row)
        if not rows:
            QMessageBox.warning(self, "Warning", "No synced loaded cameras to save.")
            return
        actual_csv_path = self._append_rows_with_permission_recovery(csv_path, rows)
        if not actual_csv_path:
            return
        csv_path = actual_csv_path
        self._update_save_log_preview(csv_path, rows)
        # v5.2: CSV refresh may happen while the window is maximized on Wayland.
        # The helper is a no-op on Wayland/maximized windows to avoid hard crash.
        self._clamp_window_to_screen_later()
        self.saved_count += 1
        self.saved_label.setText(f"Saved clips: {self.saved_count}")
        print("Saved rows:")
        print(self.last_save_log_text)
        self.annot_start_offset = None
        self.annot_end_offset = None
        self._set_field("start_sec", "")
        self._set_field("end_sec", "")
        self._update_status()
        self._focus_navigation_mode_later()
        # v4.9: Do NOT show a modal QMessageBox after every save.
        # On WSL/XWayland/Wayland, repeatedly opening the success dialog after
        # Ctrl+S could make the main window appear shifted sideways or trigger
        # a fragile window-manager resize. The bottom cumulative CSV table and
        # the status text below are enough confirmation, while warnings/errors
        # still use message boxes.
        try:
            self.status_label.setText(
                f"Saved {len(rows)} rows → {os.path.basename(csv_path)} | "
                "bottom CSV table refreshed; double-click cells to edit"
            )
        except Exception:
            pass
        self._focus_navigation_mode_later()

    # --------------------------------------------------------
    # Metadata interactions
    # --------------------------------------------------------
    def _one_person_toggled(self, checked: bool):
        if checked:
            self._set_combo("num_persons", "1")
            self._set_combo("multi_person", "no")
            if self._get_field("quality") == "invalid":
                self._set_combo("quality", "valid")

    def _num_persons_changed(self, value: str):
        if value != "1" and self.chk_one_person.isChecked():
            self.chk_one_person.setChecked(False)
        if value == "0":
            self._set_combo("multi_person", "no")
            self._set_combo("quality", "invalid")
        elif value == "1":
            self._set_combo("multi_person", "no")
            if self._get_field("quality") == "invalid":
                self._set_combo("quality", "valid")
        elif value in ["2", "3+"]:
            self._set_combo("multi_person", "yes")
            if self._get_field("quality") == "valid":
                self._set_combo("quality", "ambiguous")
        else:
            self._set_combo("multi_person", "unknown")

    def closeEvent(self, event):
        for cam in self.cams:
            if cam.cap is not None:
                cam.cap.release()
        super().closeEvent(event)

# ============================================================
# Main
# ============================================================

def main():
    _set_qt_application_attributes(QApplication, Qt)
    app = QApplication(sys.argv)
    ui_scale = get_ui_scale()
    app.setStyleSheet(make_stylesheet(ui_scale))
    print_startup_diagnostics()
    print(f"[startup] APP_VERSION: {APP_VERSION}")
    print(f"[startup] APP_TITLE: {APP_TITLE}")
    print(f"[startup] UI scale: {ui_scale:.2f}")
    print(f"[startup] Native file dialog: {_use_native_file_dialog()}")
    print(f"[startup] QT_QPA_PLATFORM: {os.environ.get('QT_QPA_PLATFORM', '(auto)')}")
    if _is_wsl() and os.environ.get('QT_QPA_PLATFORM', '').lower() == 'xcb':
        print("[startup] WSL detected: using xcb/XWayland to avoid Wayland maximized-window buffer mismatch crashes.")
    elif _is_wsl() and os.environ.get("FHP_XCB_SKIPPED_MISSING_CURSOR") == "1":
        print("[startup] WSL detected: xcb deps missing, so Qt will use Wayland/auto. If saving/maximize crashes, install libxcb-cursor0 and rerun.")
    win = AnnotationApp(ui_scale=ui_scale)
    win.showNormal()
    sys.exit(_qt_app_exec(app))

if __name__ == "__main__":
    main()
