from os.path import join
import sys

from footnotes.footnotes import Docx
from footnotes.parsing import Parseable
from footnotes.perma import make_permas
from footnotes.text import Insertion

with open(join(sys.path[0], 'abbreviations.txt')) as f:
    abbreviations = set((a.strip() for a in f if a.endswith('.\n')))
    print("Found {} abbreviations.".format(len(abbreviations)))

with Docx(sys.argv[1]) as docx:
    footnotes = docx.footnote_list

    urls = []
    for fn in footnotes:
        urls.extend(Parseable(fn.text_refs()).links())

    permas = make_permas([str(url) for url in urls])

    insertions = []
    for url in urls:
        url_str = str(url)
        if url_str in permas:
            insertions.append(url.insert_after(' [{}]'.format(permas[url_str])))

    print('Applying insertions.')
    Insertion.apply_all(insertions)

    print('Removing hyperlinks.')
    footnotes.remove_hyperlinks()

    docx.write(sys.argv[1][:-5] + '_perma.docx')
