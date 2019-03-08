import argparse
from collections import namedtuple
from itertools import chain
import json
from os.path import basename, dirname, join
import re
import sys
from urllib.parse import urlencode

from footnotes.footnotes import Docx
from footnotes.parsing import Parseable
from footnotes.spreadsheet import Spreadsheet

parser = argparse.ArgumentParser(description='Create pull spreadsheet.')
parser.add_argument('docx', help='Input Word file.')

args = parser.parse_args()

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

with open(join(sys.path[0], 'config.json')) as f:
    config = json.load(f)

with open(join(sys.path[0], 'abbreviations.txt')) as f:
    abbreviations = set(a.strip() for a in f if a.endswith('.\n'))
    abbreviations = abbreviations | set(a[:-1] + 's.' for a in abbreviations if a.endswith('.') and not a.endswith('s.'))
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

    reporters_noperiods=set(r.replace('.', '') for r in reporters)

    print("Found {} reporter abbreviations.".format(len(reporters)))

with Docx(args.docx) as docx:
    footnotes = docx.footnote_list
    spreadsheet = Spreadsheet(columns=['First FN', 'Second FN', 'Citation', 'Type', 'Source', 'Pulled', 'Puller', 'Notes'])

    for fn in footnotes:
        if fn.id() <= 0: continue

        parsed = Parseable(fn.text_refs())
        citation_sentences = parsed.citation_sentences(abbreviations | reporters_spaces)
        for idx, sentence in enumerate(citation_sentences):
            # print(str(sentence).strip())
            if not sentence.is_new_citation():
                # print('    skipping')
                continue

            pull_info = PullInfo(first_fn='{}.{}'.format(fn.id() - 2, idx + 1), second_fn=None, citation=str(sentence).strip())

            links = sentence.link_strs()
            if links:
                pull_info.notes = links[0]

            match = sentence.citation()
            if not match:
                spreadsheet.append(pull_info.out_dict())
                continue

            citation_text = str(match.citation)
            citation_type = 'Other'
            if match.source in reporters:
                citation_type = 'Case'
            elif match.source in ['Cong.Rec.', 'CongressionalRecord', 'Cong.Globe']:
                citation_type = 'Congress'
            elif match.source == 'Stat.':
                citation_type = 'Statute'

            if match.source in ['USC', 'U.S.C.']:
                section_range = r'[0-9]+([-–—][0-9]+)?'
                if re_match:
                    title = match.volume
                    section = match.subdivisions[0][0]
                    pull_info.notes = 'https://www.govinfo.gov/link/uscode/{}/{}?{}'.format(title, sections, urlencode({
                        'link-type': 'pdf',
                        'type': 'usc',
                        'year': config['govinfo']['uscode_year'],
                    }))

            if (match.source in ['U.S.', 'Stat.']
                    or citation_type == 'Congress'
                    or (citation_type == 'Other' and re.search(r'L\.|J\.|Rev\.', match.source))):
                pull_info.notes = 'https://heinonline.org/HOL/OneBoxCitation?{}'.format(urlencode({ 'cit_string': citation_text }))

            if match.source in ['Fed.Reg.', 'F.R.']:
                re_match = re.match(r'(?P<volume>[0-9]+) (F\. ?R\.|Fed\. ?Reg\.) (?P<page>[0-9,]+)', citation_text)
                volume = int(re_match.group('volume'))
                page = int(re_match.group('page').replace(',', ''))
                pull_info.notes = 'https://www.govinfo.gov/link/fr/{}/{}?{}'.format(volume, page, urlencode({
                    'link-type': 'pdf',
                }))

            if citation_type == 'Case':
                if not pull_info.notes:
                    pull_info.notes = 'https://1.next.westlaw.com/Search/Results.html?{}'.format(urlencode({
                        'query': citation_text,
                        'jurisdiction': 'ALLCASES',
                    }))

            pull_info.source = str(match.citation).strip()
            pull_info.citation_type = citation_type

            spreadsheet.append(pull_info.out_dict())

            print('{} {} citation: {}'.format(fn.id(), citation_type, match.citation))

    in_name = basename(args.docx)
    if not in_name.endswith('.docx'):
        in_name += '.docx'
    out_name = 'Bookpull.{}.xlsx'.format(in_name[:-5])
    spreadsheet.write_xlsx_path(join(dirname(args.docx), out_name))
