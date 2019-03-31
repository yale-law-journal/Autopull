import sys

from footnotes.perma import apply_file

# Look for any number of non-alpha characters followed by perma link.
in_filename = sys.argv[1]
out_filename = sys.argv[1][:-5] + '_perma.docx'

apply_file(in_filename, out_filename)
