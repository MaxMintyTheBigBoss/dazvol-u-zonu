# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('permit_update_gui.py', '.'),
        ('permitunified', 'permitunified'),
    ],
    hiddenimports=[
        'tkcalendar',
        'babel',
        'babel.numbers',
        'openpyxl',
        'permit_update',
        'permit_update_gui',
        'permitunified',
        'permitunified.procedures',
        'permitunified.db',
        'permitunified.generator',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='dazvol_u_zonu',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # без UPX
    runtime_tmpdir=None,  # распаковка в каталог .exe, а не в Temp
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)