from os.path import join
import sys

from footnotes.footnotes import FootnoteList
from footnotes.parsing import Parseable

with open(join(sys.path[0], 'abbreviations.txt')) as f:
    abbreviations = set((a.strip() for a in f if a.endswith('.\n')))
    print("Found {} abbreviations.".format(len(abbreviations)))

footnotes = FootnoteList.from_docx(sys.argv[1])
for fn in footnotes:
    if fn.id() <= 0: continue
    for para in fn.paragraphs:
        parsed = Parseable(para.text_refs())
        citation_sentences = parsed.citation_sentences(abbreviations)
        if len(citation_sentences) > 1:
            for citation in citation_sentences:
                print(fn.id(), citation)
