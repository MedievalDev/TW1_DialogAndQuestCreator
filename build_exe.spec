# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for TW1QuestCreator.exe (plan 2.1 / M9).
# Build: build_exe.bat  (one file, no console, own icon)
# The exe contains no game data: base files are extracted from the user's
# own installation into %LOCALAPPDATA%\TW1QuestCreator on the first start.

block_cipher = None

a = Analysis(
    ['TW1QuestCreator.pyw'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('README.md', '.'),
        ('questforge2/assets/icon.png', 'questforge2/assets'),
        ('questforge2/assets/icon64.png', 'questforge2/assets'),
        ('questforge2/assets/icon.ico', 'questforge2/assets'),
        ('questforge2/templates/*.json', 'questforge2/templates'),
    ],
    hiddenimports=['tw1_lan', 'tw1_qtx', 'tw1_wd', 'wdio', 'winreg'],
    hookspath=[],
    runtime_hooks=[],
    excludes=['numpy', 'PIL', 'matplotlib', 'pandas', 'scipy', 'IPython',
              'pydoc', 'unittest', 'test', 'lib2to3', 'sqlite3',
              'xmlrpc', 'multiprocessing',
              'questforge2.tests', 'quest_creator_gui', 'questforge',
              'mod_manager_gui', 'voice_index'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='TW1QuestCreator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon='questforge2/assets/icon.ico',
)
