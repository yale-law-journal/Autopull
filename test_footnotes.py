import sys
import lxml.etree as ET

from footnotes.footnotes import FootnoteList, NS
from footnotes.parsing import Parseable
NS, Parseable

fns = FootnoteList.from_docx(sys.argv[1])
fnl = fns.footnotes
f = fnl[65]
p = Parseable(f.text_refs())

def dump(elem):
    print(ET.tostring(elem, pretty_print=True).decode('utf-8'))

with open('abbreviations.txt') as f:
    abbreviations = set((a.strip() for a in f if a.endswith('.\n')))

import IPython
IPython.embed()
