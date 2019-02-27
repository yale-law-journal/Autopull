from collections import namedtuple
from itertools import chain
import json
from os.path import join
import re
import sys

from footnotes.footnotes import Docx
from footnotes.parsing import Parseable
from footnotes.spreadsheet import Spreadsheet

class PullInfo(object):
    def __init__(self, first_fn, second_fn, citation, citation_type='',
                 source='', pulled='', puller='', notes=''):
        self.first_fn = first_fn
        self.second_fn = second_fn
        self.citation = citation
        self.citation_type = citation_type
        self.source = source
        self.pulled = pulled
        self.puller = puller
        self.notes = notes

    def out_dict(self):
        return {
            'First FN': self.first_fn,
            'Second FN': self.second_fn,
            'Citation': self.citation,
            'Type': self.citation_type,
            'Source': self.source,
            'Pulled': self.pulled,
            'Puller': self.puller,
            'Notes': self.notes,
        }

with open(join(sys.path[0], 'abbreviations.txt')) as f:
    abbreviations = set((a.strip() for a in f if a.endswith('.\n')))
    print("Found {} abbreviations.".format(len(abbreviations)))

with open(join(sys.path[0], 'reporters-db', 'reporters_db', 'data', 'reporters.json')) as f:
    reporters_json = json.load(f)
    reporters_infos = chain.from_iterable(reporters_json.values())
    reporters_variants = chain.from_iterable(info['variations'].items() for info in reporters_infos)
    reporters_spaces = set(chain.from_iterable(reporters_variants))
    reporters = set(r.replace(' ', '') for r in reporters_spaces)

    # This is a weird special case.
    reporters.remove('Tex.L.Rev.')
    reporters.remove('TexasL.Rev.')

    print("Found {} reporter abbreviations.".format(len(reporters)))

with Docx(sys.argv[1]) as docx:
    footnotes = docx.footnote_list
    spreadsheet = Spreadsheet(columns=['First FN', 'Second FN', 'Citation', 'Type', 'Source', 'Pulled', 'Puller', 'Notes'])

    for fn in footnotes:
        if fn.id() <= 0: continue
        for para in fn.paragraphs:
            parsed = Parseable(para.text_refs())
            citation_sentences = parsed.citation_sentences(abbreviations | reporters_spaces)
            for idx, sentence in enumerate(citation_sentences):
                pull_info = PullInfo(first_fn='{}.{}'.format(fn.id() - 2, idx + 1), second_fn=None, citation=str(sentence).strip())

                links = sentence.link_strs()
                if links:
                    pull_info.notes = links[0]

                match = sentence.citation()
                if not match:
                    spreadsheet.append(pull_info.out_dict())
                    continue

                citation_type = 'Other'
                if match.source in reporters:
                    citation_type = 'Case'
                elif match.source in ['Cong.Rec.', 'CongressionalRecord', 'Cong.Globe']:
                    citation_type = 'Congress'
                elif match.source == 'Stat.':
                    citation_type = 'Statute'

                pull_info.source = str(match.citation).strip()
                pull_info.citation_type = citation_type

                spreadsheet.append(pull_info.out_dict())

                print('{} {} citation: {}'.format(fn.id(), citation_type, match.citation))

    spreadsheet.write_xlsx_path('pull.xlsx')
