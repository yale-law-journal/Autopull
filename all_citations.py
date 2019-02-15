import sys

from footnotes.footnotes import FootnoteList
from footnotes.parsing import Paragraph

with open('abbreviations.txt') as f:
    abbreviations = set((a.strip() for a in f if a.endswith('.\n')))
    print("Found {} abbreviations.".format(len(abbreviations)))

footnotes = FootnoteList.from_docx(sys.argv[1])
for fn in footnotes:
    if fn.id() <= 0: continue
    for para in fn.paragraphs:
        text_para = Paragraph(para.text())
        citation_sentences = text_para.citation_sentences(abbreviations)
        if len(citation_sentences) > 1:
            for citation in citation_sentences:
                print(fn.id(), citation)
