import sys
import lxml.etree as ET

from footnotes.footnotes import FootnoteList, NS
from footnotes.parsing import Paragraph
NS

fns = FootnoteList.from_docx(sys.argv[1])
fnl = fns.footnotes

def dump(elem):
    print(ET.tostring(elem, pretty_print=True).decode('utf-8'))

with open('abbreviations.txt') as f:
    abbreviations = set((a.strip() for a in f if a.endswith('.\n')))

import IPython
IPython.embed()
