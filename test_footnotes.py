import sys
import lxml.etree as ET

from footnotes.footnotes import Docx, NS
from footnotes.parsing import Parseable
NS, Parseable

with Docx(sys.argv[1]) as docx:
    fns = docx.footnote_list
    fnl = fns.footnotes
    f = fnl[65]
    p = Parseable(f.text_refs())

    def dump(elem):
        print(ET.tostring(elem, pretty_print=True).decode('utf-8'))

    import IPython
    IPython.embed()
