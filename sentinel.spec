# sentinel.spec
# PyInstaller specification file for the Ghost Trail desktop application.
# Run with:  pyinstaller sentinel.spec

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

# ─────────────────────────────────────────────────────────────────────────────
# Collect data files from installed packages
# ─────────────────────────────────────────────────────────────────────────────

datas = []

# ultralytics (YOLOv8) — needs its assets and cfg files
try:
    datas += collect_data_files("ultralytics")
except Exception:
    pass

# supervision
try:
    datas += collect_data_files("supervision")
except Exception:
    pass

# torchreid
try:
    datas += collect_data_files("torchreid")
except Exception:
    pass

# insightface
try:
    datas += collect_data_files("insightface")
except Exception:
    pass

# pywebview — needs its HTML/JS resources
try:
    datas += collect_data_files("webview")
except Exception:
    pass

# ── Project-specific data files ────────────────────────────────────────────
project_datas = [
    # (source_path_or_glob, dest_dir_inside_bundle)
    ("config.yaml",          "."),
    ("yolov8n.pt",           "."),
    ("tracker.db",           "."),
    ("Faces",                "Faces"),
    ("dashboard/dist",       "dashboard/dist"),
]
datas += project_datas

# ─────────────────────────────────────────────────────────────────────────────
# Hidden imports that PyInstaller can't auto-detect
# ─────────────────────────────────────────────────────────────────────────────

hiddenimports = [
    # FastAPI / Uvicorn internals
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "fastapi",
    "fastapi.middleware.cors",
    "fastapi.staticfiles",
    "fastapi.responses",
    "starlette.middleware.cors",
    "starlette.staticfiles",
    "anyio",
    "anyio._backends._asyncio",
    "anyio._backends._trio",
    # PyYAML
    "yaml",
    # OpenCV
    "cv2",
    # NumPy / SciPy
    "numpy",
    "scipy.spatial",
    "scipy.optimize",
    # Torch
    "torch",
    "torchvision",
    # torchreid
    "torchreid",
    "torchreid.models",
    "torchreid.utils",
    # supervision
    "supervision",
    # ultralytics
    "ultralytics",
    # insightface
    "insightface",
    "insightface.app",
    "insightface.model_zoo",
    # pywebview backends
    "webview",
    "webview.platforms",
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
    # pystray + PIL
    "pystray",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFont",
    # multiprocessing
    "multiprocessing",
    "multiprocessing.freeze_support",
    # Sentinel modules
    "sentinel_server",
    "sentinel_tracker",
    "alert_manager",
    "database",
    "detector",
    "face_recognizer",
    "identity_manager",
    "stream_manager",
    "tracker",
]

# ─────────────────────────────────────────────────────────────────────────────
# Analysis
# ─────────────────────────────────────────────────────────────────────────────

a = Analysis(
    ["sentinel_app.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy unused packages
        "matplotlib",
        "IPython",
        "jupyter",
        "notebook",
        "pytest",
        "black",
        "isort",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,         # Use COLLECT for cleaner distribution
    name="sentinel",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                     # Disable UPX — can break torch DLLs
    console=False,                 # NO console window — pure GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/tray_icon.ico",   # App icon (created by build script)
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="sentinel",               # Output folder: dist/sentinel/
)
