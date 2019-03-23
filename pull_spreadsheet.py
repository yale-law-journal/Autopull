import aiohttp
import asyncio
import argparse
import certifi
from itertools import chain
import json
import mimetypes
from os.path import basename, dirname, join
import re
import ssl
import sys
from urllib.parse import urlencode
import zipfile

from footnotes.config import CONFIG
from footnotes.footnotes import Docx
from footnotes.parsing import abbreviations, CitationContext, normalize, Parseable, Subdivisions
from footnotes.spreadsheet import Spreadsheet

parser = argparse.ArgumentParser(description='Create pull spreadsheet.')
parser.add_argument('docx', help='Input Word file.')
parser.add_argument('--pull', action='store_true', help='Attempt to pull sources.')

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

def short_title(title):
    return re.sub(r'[^A-Za-z0-9]', '', ''.join(title.split(' ')[:6]))[:30]

async def download_file_zip(zipf, session, url, name, pull_info):
    # print('Downloading [{}] -> [{}]...'.format(url, name))
    buf = bytearray()
    try:
        async with session.get(url) as response:
            if response.status not in [200, 201]:
                return

            async for data, _ in response.content.iter_chunks():
                buf += data

            if 'octet-stream' not in response.content_type:
                extension = mimetypes.guess_extension(response.content_type)
                if not name.endswith(extension):
                    name += extension

        with zipf.open(zipfile_name[:-4] + '/' + name, 'w') as f:
            f.write(buf)

        pull_info.pulled = 'Y'
    except Exception: pass

async def process_footnotes(footnotes, zipf=None, session=None):
    pull_infos = []
    downloads = []
    citation_context = CitationContext()
    for fn in footnotes:
        if not fn.text().strip(): continue

        parsed = Parseable(fn.text_refs())
        citation_sentences = parsed.citation_sentences(abbreviations | reporters_spaces)
        for idx, sentence in enumerate(citation_sentences):
            # print('Sentence:', str(sentence).strip())
            if not citation_context.is_new_citation(sentence):
                # print('    skipping')
                continue

            pull_info = PullInfo(first_fn='{}.{}'.format(fn.number, idx + 1), second_fn=None, citation=str(sentence).strip())
            pull_infos.append(pull_info)
            pull_info.citation_type = 'Other'

            links = sentence.link_strs()
            if links:
                pull_info.citation_type = 'Link'
                pull_info.notes = links[0]

            match = sentence.citation()
            if not match: continue

            citation_text = normalize(str(match.citation))
            if match.source in reporters:
                pull_info.citation_type = 'Case'
            elif match.source in ['Cong.Rec.', 'CongressionalRecord', 'Cong.Globe']:
                pull_info.citation_type = 'Congress'
            elif match.source == 'Stat.':
                pull_info.citation_type = 'Statute'
            elif re.search(r'Law|Review|Journal|(L|J|Rev|REV)\.', match.source):
                pull_info.citation_type = 'Journal'

            if match.source in ['USC', 'U.S.C.'] and match.subdivisions.ranges:
                pull_info.citation_type = 'Code'
                title = match.volume
                range_start = match.subdivisions.ranges[0][0]
                start_match = re.match(Subdivisions.SECTION, range_start)
                if start_match:
                    section = start_match.group(0)
                    pull_info.notes = 'https://www.govinfo.gov/link/uscode/{}/{}?{}'.format(title, section, urlencode({
                        'link-type': 'pdf',
                        'type': 'usc',
                        'year': CONFIG['govinfo']['uscode_year'],
                    }))

            if pull_info.citation_type in ['Congress', 'Journal', 'Statute']:
                pull_info.notes = 'https://heinonline.org/HOL/OneBoxCitation?{}'.format(urlencode({ 'cit_string': citation_text }))

            if match.source == 'U.S.':
                pull_info.notes = 'https://cdn.loc.gov/service/ll/usrep/usrep{volume:03d}/usrep{volume:03d}{page:03d}/usrep{volume:03d}{page:03d}.pdf'.format(
                    volume=match.volume, page=int(match.subdivisions.ranges[0][0])
                )

            if match.source in ['Fed.Reg.', 'F.R.']:
                re_match = re.match(r'(?P<volume>[0-9]+) (F\. ?R\.|Fed\. ?Reg\.) (?P<page>[0-9,]+)', citation_text)
                volume = int(re_match.group('volume'))
                page = int(re_match.group('page').replace(',', ''))
                pull_info.notes = 'https://www.govinfo.gov/link/fr/{}/{}?{}'.format(volume, page, urlencode({
                    'link-type': 'pdf',
                }))

            if pull_info.citation_type == 'Case' and not pull_info.notes:
                pull_info.notes = 'https://1.next.westlaw.com/Search/Results.html?{}'.format(urlencode({
                    'query': citation_text,
                    'jurisdiction': 'ALLCASES',
                }))

            pull_info.source = str(match.citation).strip()

            if zipf is not None:
                short_citation = re.sub(r'[^A-Za-z0-9]', '', pull_info.source)
                if pull_info.citation_type == 'Journal':
                    title = normalize(str(match.find_title()))
                    url = CONFIG['pdfapi']['url'] + '/api/articles/{}/{}/{}'.format(match.original_source, match.volume, title)
                    name = '{}.{}.{}'.format(pull_info.first_fn, short_citation, short_title(title))
                    downloads.append(download_file_zip(zipf, session, url, name, pull_info))
                elif pull_info.notes and 'westlaw' not in pull_info.notes and 'heinonline' not in pull_info.notes:
                    name = '{}.{}'.format(pull_info.first_fn, short_citation)
                    downloads.append(download_file_zip(zipf, session, pull_info.notes, name, pull_info))

    def format(workbook, worksheet):
        green = workbook.add_format()
        green.set_bg_color('#d9ead3')
        red = workbook.add_format()
        red.set_bg_color('#e6b8af')
        worksheet.conditional_format('F2:F1000', {
            'type': 'text',
            'criteria': 'containing',
            'value': 'Y',
            'format': green,
        })
        worksheet.conditional_format('F2:F1000', {
            'type': 'text',
            'criteria': 'containing',
            'value': 'N',
            'format': red,
        })

    if zipf:
        print('Waiting for downloads to complete...')
        try:
            await asyncio.wait_for(asyncio.shield(asyncio.gather(*downloads)), 60)
        except asyncio.TimeoutError: pass

        num_success = len([pi for pi in pull_infos if pi.pulled == 'Y'])
        print('Successfully pulled {} out of {} sources.'.format(num_success, len(pull_infos)))
        print('Sources pulled at {}.'.format(zipfile_name))

    spreadsheet = Spreadsheet(columns=['First FN', 'Second FN', 'Citation', 'Type', 'Source', 'Pulled', 'Puller', 'Notes'])

    for pull_info in pull_infos:
        spreadsheet.append(pull_info.out_dict())

    spreadsheet.write_xlsx_path(join(dirname(args.docx), spreadsheet_name), format)

    print('Finished. Spreadsheet at {}.'.format(spreadsheet_name))

async def pull():
    if args.pull:
        with zipfile.ZipFile(zipfile_name, 'w') as zipf:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            connector = aiohttp.TCPConnector(ssl_context=ssl_context)
            async with aiohttp.ClientSession(connector=connector) as session:
                await process_footnotes(footnotes, zipf, session)
    else:
        await process_footnotes(footnotes)

in_name = basename(args.docx)
if not in_name.endswith('.docx'):
    in_name += '.docx'
spreadsheet_name = 'Bookpull.{}.xlsx'.format(in_name[:-5])
zipfile_name = 'BookpullSources.{}.zip'.format(in_name[:-5])

with Docx(args.docx) as docx:
    footnotes = docx.footnote_list

loop = asyncio.get_event_loop()
loop.run_until_complete(pull())
