'''
Usage:
    python setup.py build
'''

from cx_Freeze import setup, Executable
from os.path import join
import sys

PACKAGE_FILES = [join('footnotes', 'config.json'), join('footnotes', 'abbreviations.txt')]
BATCH_FILES = [
    ('run_apply_perma.bat', 'Add Perma Links.bat'),
    ('run_pull_spreadsheet.bat', 'Make Pull Spreadsheet.bat')
] if sys.platform == 'win32' else []
DATA_FILES = [join('reporters-db', 'reporters_db', 'data', 'reporters.json')]

BUILD_EXE_OPTIONS = {
    'packages': ['lxml', 'aiohttp', 'asyncio', 'idna', 'certifi'],
    'excludes': ['tkinter'],
    'include_files': BATCH_FILES + [(f, f) for f in DATA_FILES] + [(f, join('lib', f)) for f in PACKAGE_FILES],
    'include_msvcr': True,
}

setup(
    name='Autopull',
    version='0.0',
    description='Tools for improving source citing for law journals.',
    options={
        'build_exe': BUILD_EXE_OPTIONS
    },
    executables=[
        Executable('apply_perma.py'),
        Executable('pull_spreadsheet.py'),
    ],
)
