import aiohttp
import asyncio
import certifi
import json
import math
from os.path import dirname, join
import re
import ssl
import sys

from .config import CONFIG
from .footnotes import Docx
from .parsing import Parseable
from .text import Insertion

API_ENDPOINT = 'https://api.perma.cc/v1/archives/batches'
API_CHUNK_SIZE = 10

class SyncSession(aiohttp.ClientSession):
    def __enter__(self):
        return run(self.__aenter__())

    def __exit__(self, *args):
        return run(self.__aexit__(*args))

def run(coroutine):
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(coroutine)
    return result

def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i + n]

async def make_permas_batch(session, urls, folder, result):
    data = { 'urls': urls, 'target_folder': folder }
    params = { 'api_key': CONFIG['perma']['api_key'] }

    print('Starting batch of {}...'.format(len(urls)))
    for _ in range(3):
        async with session.post(API_ENDPOINT, params=params, json=data) as response:
            # print('Status: {}; content type: {}.'.format(response.status, response.content_type))
            if response.status == 201 and response.content_type == 'application/json':
                batch = await response.json()
                # print(batch)
                print('Batch finished.')
                for job in batch['capture_jobs']:
                    result[job['submitted_url']] = 'https://perma.cc/{}'.format(job['guid'])

                return

        print('Retrying...')

def make_permas_progress(urls, permas, folder=None):
    url_strs = [str(url) for url in urls]
    print('Making permas for {} URLs.'.format(len(url_strs)))

    ssl_context = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(ssl_context=ssl_context)
    with SyncSession(connector=connector) as session:
        if folder is None:
            folder = CONFIG['perma']['folder_id']

        batches = []
        total_chunks = math.ceil(len(url_strs) / API_CHUNK_SIZE)
        for idx, chunk in enumerate(chunks(url_strs, API_CHUNK_SIZE)):
            run(make_permas_batch(session, chunk, folder, permas))
            yield { 'progress': idx + 1, 'total': total_chunks }

def make_permas(urls, folder=None):
    permas = {}
    [_ for _ in make_permas_progress(urls, permas, folder)]
    return permas

def collect_urls(footnotes):
    for fn in footnotes:
        parsed = Parseable(fn.text_refs())
        links = parsed.links()
        for span, url in links:
            rest = parsed[span.j:]
            rest_str = str(rest)
            if not PERMA_RE.match(rest_str):
                yield url

def generate_insertions(urls, permas):
    for url in urls:
        url_str = str(url)
        if url_str in permas:
            yield url.insert_after(' [{}]'.format(permas[url_str]))

PERMA_RE = re.compile(r'[^A-Za-z0-9]*(https?://)?perma.cc')
def apply_docx(docx):
    footnotes = docx.footnote_list
    urls = collect_urls(footnotes)

    permas = make_permas(urls)
    insertions = generate_insertions(urls, permas)

    print('Applying insertions.')
    Insertion.apply_all(insertions)

    print('Removing hyperlinks.')
    footnotes.remove_hyperlinks()

def apply_file(file_or_obj, out_filename):
    with Docx(file_or_obj) as docx:
        apply_docx(docx)
        docx.write(out_filename)
