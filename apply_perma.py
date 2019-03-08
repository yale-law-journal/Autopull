from os.path import join
import re
import sys

from footnotes.footnotes import Docx
from footnotes.parsing import Parseable
from footnotes.perma import make_permas
from footnotes.text import Insertion

# Look for any number of non-alpha characters followed by perma link.
PERMA_RE = re.compile(r'[^A-Za-z0-9]*(https?://)?perma.cc')

with Docx(sys.argv[1]) as docx:
    footnotes = docx.footnote_list

    urls = []
    for fn in footnotes:
        parsed = Parseable(fn.text_refs())
        links = parsed.links()
        for span, url in links:
            rest = parsed[span.j:]
            rest_str = str(rest)
            if not PERMA_RE.match(rest_str):
                urls.append(url)

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
