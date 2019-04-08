import argparse

from footnotes.config import CONFIG
from footnotes.pull import pull_local

parser = argparse.ArgumentParser(description='Create pull spreadsheet.')
parser.add_argument('docx', help='Input Word file.')
parser.add_argument('--no-pull', action='store_true', help='Don\'t attempt to pull sources.')
parser.add_argument('--debug', action='store_true', help='Print debug information.')

cli_args = parser.parse_args()

if cli_args.debug:
    CONFIG['mode'] = 'development'

pull_local(cli_args.docx, not cli_args.no_pull)
