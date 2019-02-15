import sys
import lxml.etree as ET

from footnotes.footnotes import FootnoteList, NS

fns = FootnoteList.from_file(sys.argv[1])
fnl = fns.footnotes

def dump(elem):
    print(ET.tostring(elem, pretty_print=True).decode('utf-8'))

import IPython
IPython.embed()
