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
        'babel.dates',
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
    # КРИТИЧНО: исключаем pkg_resources и setuptools
    # Из-за них tkinter / tkcalendar тянет jaraco.text, который
    # пытается прочитать Lorem ipsum.txt и падает.
    excludes=[
        'pkg_resources',
        'pkg_resources.py2_warn',
        'setuptools',
        'setuptools._vendor',
        'setuptools._vendor.jaraco',
        'setuptools._vendor.jaraco.text',
        'jaraco.text',
        'pyi_rth_pkgres',
    ],
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
    name='dazvol_u_zony0.0.7',  # имя с версией
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