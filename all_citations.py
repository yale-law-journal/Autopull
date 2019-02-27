from itertools import chain
import json
from os.path import join
import re
import sys

from footnotes.footnotes import Docx
from footnotes.parsing import Parseable

with open(join(sys.path[0], 'abbreviations.txt')) as f:
    abbreviations = set((a.strip() for a in f if a.endswith('.\n')))
    print("Found {} abbreviations.".format(len(abbreviations)))

with open(join(sys.path[0], 'reporters-db', 'reporters_db', 'data', 'reporters.json')) as f:
    reporters_json = json.load(f)
    reporters_infos = chain.from_iterable(reporters_json.values())
    reporters_variants = chain.from_iterable(info['variations'].items() for info in reporters_infos)
    reporters_spaces = set(chain.from_iterable(reporters_variants))
    reporters = set(r.replace(' ', '') for r in reporters_spaces)
    print("Found {} reporter abbreviations.".format(len(reporters)))

with Docx(sys.argv[1]) as docx:
    footnotes = docx.footnote_list
    for fn in footnotes:
        if fn.id() <= 0: continue
        for para in fn.paragraphs:
            parsed = Parseable(para.text_refs())
            citation_sentences = parsed.citation_sentences(abbreviations | reporters_spaces)
            for sentence in citation_sentences:
                match = sentence.citation(reporters=reporters)
                if match:
                    print(fn.id(), match)
