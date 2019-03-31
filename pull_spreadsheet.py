import argparse

from footnotes.pull import pull_local

parser = argparse.ArgumentParser(description='Create pull spreadsheet.')
parser.add_argument('docx', help='Input Word file.')
parser.add_argument('--no-pull', action='store_true', help='Don\'t attempt to pull sources.')

cli_args = parser.parse_args()

pull_local(cli_args.docx, not cli_args.no_pull)
