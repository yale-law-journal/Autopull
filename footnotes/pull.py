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
import string
import sys
from urllib.parse import urlencode
import zipfile

from footnotes.config import CONFIG
from footnotes.footnotes import Docx
from footnotes.parsing import abbreviations, CitationContext, normalize, Parseable, Subdivisions
from footnotes.spreadsheet import Spreadsheet

def dprint(*args, **kwargs):
    if 'mode' in CONFIG and CONFIG['mode'] == 'development':
        try:
            print(*args, **kwargs)
        except UnicodeEncodeError:
            pass  # print(*(filter(lambda c: c in string.printable, s) for s in args), **kwargs)

with open(join(sys.path[0], 'reporters-db', 'reporters_db', 'data', 'reporters.json')) as f:
    reporters_json = json.load(f)
    reporters_infos = chain.from_iterable(reporters_json.values())
    reporters_variants = chain.from_iterable(info['variations'].items() for info in reporters_infos)
    reporters_spaces = set(chain.from_iterable(reporters_variants))
    reporters = set(r.replace(' ', '') for r in reporters_spaces)

    # This is a weird special case.
    reporters.remove('Tex.L.Rev.')
    reporters.remove('TexasL.Rev.')

    reporters.add('WL')
    reporters.add('U.S.Dist.LEXIS')
    reporters.add('U.S.App.LEXIS')

    reporters_noperiods=set(r.replace('.', '') for r in reporters)

class PullInfo(object):
    def __init__(self, first_fn, second_fn, citation, citation_type='',
                 source='', pulled='', puller='', human_link='',
                 download_link='', download_name=''):
        self.first_fn = first_fn
        self.second_fn = second_fn
        self.citation = citation
        self.citation_type = citation_type
        self.source = source
        self.pulled = pulled
        self.puller = puller
        self.human_link = human_link
        self.download_link = download_link
        self.download_name = download_name

    def out_dict(self):
        return {
            'First FN': self.first_fn,
            'Second FN': self.second_fn,
            'Citation': self.citation,
            'Type': self.citation_type,
            'Source': self.source,
            'Pulled': self.pulled,
            'Puller': self.puller,
            'Notes': self.human_link,
        }

def short_title(title):
    return re.sub(r'[^A-Za-z0-9]', '', ''.join(title.split(' ')[:6]))[:30]

# These links work if they don't return 404.
# Unfortunately, some news orgs don't return 404 when accessing invalid link.
WHITELIST = ['nytimes.com/', 'npr.org/', 'vox.com/', 'whitehouse.gov/', 'cnn.com/']
async def download_file_check(context, url, pull_info):
    try:
        async with context.session.head(url, allow_redirects=True) as response:
            dprint('Checking link [{}]: {}'.format(url, response.content_type))
            if response.status in [200, 201]:
                if (response.content_type == 'application/pdf'
                        or any(site in url for site in WHITELIST)):
                    pull_info.pulled = 'Link works'
    except Exception: pass

async def download_file_zip(context, url, name, pull_info):
    buf = bytearray()
    try:
        async with context.session.get(url) as response:
            dprint('{} downloading [{}] -> [{}]...'.format(response.status, url, name))
            if response.status not in [200, 201]:
                return

            async for data, _ in response.content.iter_chunks():
                buf += data

            if 'octet-stream' not in response.content_type:
                extension = mimetypes.guess_extension(response.content_type)
                if not name.endswith(extension):
                    name += extension

        with context.zipf.open(context.zipfile_prefix + '/' + name, 'w') as f:
            f.write(buf)

        pull_info.pulled = 'Y'
    except Exception: pass

def pull(context):
    pull_infos = []
    downloads = []
    citation_context = CitationContext()
    for fn in context.footnotes:
        if not fn.text().strip(): continue

        parsed = Parseable(fn.text_refs())
        citation_sentences = parsed.citation_sentences(abbreviations | reporters_spaces)
        for idx, sentence in enumerate(citation_sentences):
            dprint('Sentence:', str(sentence).strip())
            if not citation_context.is_new_citation(sentence, reporters=reporters):
                # print('    skipping')
                continue

            sentence_text = normalize(str(sentence)).strip()

            pull_info = PullInfo(first_fn='{}.{}'.format(fn.number, idx + 1), second_fn=None, citation=str(sentence).strip())
            pull_infos.append(pull_info)
            pull_info.citation_type = 'Other'

            links = sentence.link_strs()
            if links:
                pull_info.citation_type = 'Link'
                pull_info.human_link = links[0]
                if links[0].endswith('.pdf'):
                    pull_info.download_link = pull_info.human_link

            if re.search(r'S\. ?((Exec\. |Treaty )?Doc|Rept?)\.|H\. ?R\. ((Misc\. )?Doc|Rept?)\.', sentence_text):
                pull_info.citation_type = 'Legislative History'
                pull_info.human_link = 'https://congressional.proquest.com/congressional/search/searchbynumber/bynumber?#Bibliographic_Citations'

            if re.search(r'U\. ?S\. Const(\.|itution)', sentence_text):
                pull_info.citation_type = 'Constitution'
                pull_info.human_link = 'https://www.archives.gov/founding-docs/constitution-transcript'
                pull_info.download_link = pull_info.human_link
                pull_info.download_name = 'USConstitution'

            match = sentence.citation()
            if match:
                citation_text = normalize(str(match.citation))
                short_citation = re.sub(r'[^A-Za-z0-9]', '', citation_text)

                if match.source in reporters:
                    pull_info.citation_type = 'Case'
                elif match.source in ['Cong.Rec.', 'CongressionalRecord', 'Cong.Globe']:
                    pull_info.citation_type = 'Congress'
                elif match.source == 'Stat.':
                    pull_info.citation_type = 'Statute'
                elif match.source in ['Fed.Reg.', 'F.R.']:
                    pull_info.citation_type = 'Administrative'
                elif re.search(r'Law|Review|Journal|(L|J|Rev|REV)\.', match.source):
                    pull_info.citation_type = 'Journal'

                if match.source in ['USC', 'U.S.C.'] and match.subdivisions.ranges:
                    pull_info.citation_type = 'Code'
                    title = match.volume
                    range_start = match.subdivisions.ranges[0][0]
                    start_match = re.match(Subdivisions.SECTION, range_start)
                    if start_match:
                        section = start_match.group(0)
                        pull_info.human_link = 'https://www.govinfo.gov/link/uscode/{}/{}?{}'.format(title, section, urlencode({
                            'link-type': 'pdf',
                            'type': 'usc',
                            'year': CONFIG['govinfo']['uscode_year'],
                        }))
                        pull_info.download_link = pull_info.human_link

                if pull_info.citation_type in ['Congress', 'Journal', 'Statute'] or match.source == 'U.S.':
                    pull_info.human_link = 'https://heinonline.org/HOL/OneBoxCitation?{}'.format(urlencode({ 'cit_string': citation_text }))

                if pull_info.citation_type == 'Journal':
                    title = normalize(str(match.find_title()))
                    pull_info.download_link = CONFIG['pdfapi']['url'] + '/api/articles/{}/{}/{}'.format(match.original_source, match.volume, title)
                    pull_info.download_name = '{}.{}'.format(short_citation, short_title(title))

                if pull_info.citation_type == 'Statute' and match.volume >= 65:
                    page_str = match.subdivisions.ranges[0][0]
                    if page_str and page_str.isdigit():
                        pull_info.download_link = 'https://www.govinfo.gov/link/statute/{}/{}?link-type=pdf'.format(
                            match.volume, int(page_str)
                        )

                if match.source == 'U.S.':
                    if match.volume < 502:
                        pull_info.download_link = 'https://cdn.loc.gov/service/ll/usrep/usrep{volume:03d}/usrep{volume:03d}{page:03d}/usrep{volume:03d}{page:03d}.pdf'.format(
                            volume=match.volume, page=int(match.subdivisions.ranges[0][0])
                        )
                    else:
                        pull_info.download_link = CONFIG['pdfapi']['url'] + '/api/cases/{}/{}/{}'.format(
                            match.source, match.volume, match.subdivisions.ranges[0][0]
                        )

                if pull_info.citation_type == 'Administrative':
                    re_match = re.match(r'(?P<volume>[0-9]+) (F\. ?R\.|Fed\. ?Reg\.) (?P<page>[0-9,]+)', citation_text)
                    volume = int(re_match.group('volume'))
                    page = int(re_match.group('page').replace(',', ''))
                    pull_info.human_link = 'https://www.govinfo.gov/link/fr/{}/{}?{}'.format(volume, page, urlencode({
                        'link-type': 'pdf',
                    }))
                    pull_info.download_link = pull_info.human_link

                if pull_info.citation_type == 'Case' and not pull_info.human_link:
                    pull_info.human_link = 'https://1.next.westlaw.com/Search/Results.html?{}'.format(urlencode({
                        'query': citation_text,
                        'jurisdiction': 'ALLCASES',
                    }))

                pull_info.source = str(match.citation).strip()
                if not pull_info.download_name:
                    pull_info.download_name = short_citation

            if context.zipf is not None and pull_info.download_link:
                if pull_info.download_name:
                    name = '{}.{}'.format(pull_info.first_fn, pull_info.download_name)
                elif pull_info.download_link.endswith('.pdf'):
                    _, _, last = pull_info.download_link.rpartition('/')
                    name = '{}.{}'.format(pull_info.first_fn, last)
                else:
                    name = '{}'.format(pull_info.first_fn)

                downloads.append(download_file_zip(context, pull_info.download_link, name, pull_info))

            if (context.session is not None
                    and pull_info.human_link
                    and not pull_info.download_link
                    and 'congressional.proquest.com' not in pull_info.human_link
                    and 'westlaw.com' not in pull_info.human_link
                    and 'heinonline.org' not in pull_info.human_link):
                # Try to download and mark as "pulled" if it's a PDF.
                downloads.append(download_file_check(context, pull_info.human_link, pull_info))

    return downloads, pull_infos

async def await_downloads(downloads, pull_infos):
    print('Trying to download {} sources.'.format(len(downloads)))
    print('Waiting for downloads to complete...')
    try:
        await asyncio.wait_for(asyncio.gather(*downloads), 120)
    except (asyncio.TimeoutError, TimeoutError):
        print('Timed out.')

    num_success = len([pi for pi in pull_infos if 'Y' in pi.pulled or 'works' in pi.pulled])
    print('Successfully pulled {} out of {} total sources.'.format(num_success, len(pull_infos)))

def write_spreadsheet(pull_infos, spreadsheet_path):
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
            'value': 'works',
            'format': green,
        })
        worksheet.conditional_format('F2:F1000', {
            'type': 'text',
            'criteria': 'containing',
            'value': 'N',
            'format': red,
        })

    spreadsheet = Spreadsheet(columns=['First FN', 'Second FN', 'Citation', 'Type', 'Source', 'Pulled', 'Puller', 'Notes'])

    for pull_info in pull_infos:
        spreadsheet.append(pull_info.out_dict())

    spreadsheet.write_xlsx_path(spreadsheet_path, format)

    print('Created spreadsheet at {}.'.format(basename(spreadsheet_path)))

class PullContext(object):
    def __init__(self, filename, zipfile_path=None, zipfile_prefix=None):
        self.filename = filename
        self.zipfile_path = zipfile_path
        self.zipfile_prefix = zipfile_prefix
        if self.zipfile_prefix is None and self.zipfile_path is not None:
            zipfile_base = basename(zipfile_path)
            self.zipfile_prefix = zipfile_base[:-4] if len(zipfile_base) > 4 else 'zip'
        self.zipf, self.session = None, None

        with Docx(filename) as docx:
            self.footnotes = docx.footnote_list

    async def __aenter__(self):
        if self.zipfile_path:
            self.zipf = zipfile.ZipFile(self.zipfile_path, 'w').__enter__()
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            connector = aiohttp.TCPConnector(ssl_context=ssl_context, limit=300)
            self.session = aiohttp.ClientSession(connector=connector)

        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        if self.zipfile_path:
            self.zipf.close()
            await self.session.close()

async def pull_local_co(filename, pull_sources=True):
    in_name = basename(filename)
    if not in_name.endswith('.docx'):
        in_name += '.docx'

    spreadsheet_name = 'Bookpull.{}.xlsx'.format(in_name[:-5])
    spreadsheet_path = join(dirname(filename), spreadsheet_name)
    zipfile_name = 'BookpullSources.{}.zip'.format(in_name[:-5])
    zipfile_path = join(dirname(filename), zipfile_name)

    async with PullContext(filename, zipfile_path if pull_sources else None) as context:
        downloads, pull_infos = pull(context)
        await await_downloads(downloads, pull_infos)
        print('Sources pulled at {}.'.format(zipfile_name))
        write_spreadsheet(pull_infos, spreadsheet_name)

def pull_local(filename, pull_sources=True):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(pull_local_co(filename, pull_sources))
