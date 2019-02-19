from os.path import join
import sys

from footnotes.footnotes import Docx
from footnotes.parsing import Parseable
from footnotes.text import Insertion

with open(join(sys.path[0], 'abbreviations.txt')) as f:
    abbreviations = set((a.strip() for a in f if a.endswith('.\n')))
    print("Found {} abbreviations.".format(len(abbreviations)))

with Docx(sys.argv[1]) as docx:
    footnotes = docx.footnote_list
    insertions = []
    for fn in footnotes:
        if fn.id() <= 0: continue

        parsed = Parseable(fn.text_refs())
        for url in parsed.links():
            insertions.append(url.insert_after(' [perma]'))

    print('Applying insertions.')
    Insertion.apply_all(insertions)

    print('Removing hyperlinks.')
    footnotes.remove_hyperlinks()

    docx.write(sys.argv[1][:-5] + '_perma.docx')
