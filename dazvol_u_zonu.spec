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
        # Данные babel — без них tkcalendar ломает Tcl при locale="ru_RU"
        # Сейчас locale убран, но оставим на всякий случай
    ],
    hiddenimports=[
        'tkcalendar',
        'babel',
        'babel.numbers',
        'babel.dates',
        'babel.messages',
        'babel.core',
        'babel.localedata',
        'babel.localtime',
        'babel.support',
        'babel.plural',
        'babel.unknown',
        'babel._compat',
        'babel._numbers',
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
    runtime_hooks=['rthook_tcl.py'],
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
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)