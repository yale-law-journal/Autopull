import aiohttp
import asyncio
import certifi
import re
import ssl

from .config import CONFIG
from .footnotes import Docx
from .parsing import Parseable
from .text import Insertion

API_ENDPOINT = 'https://api.perma.cc/v1/archives/batches'
API_CHUNK_SIZE = 8

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

async def make_permas_batch(context, urls):
    data = { 'urls': urls, 'target_folder': context.folder }
    params = { 'api_key': context.api_key }

    print('Starting batch of {}...'.format(len(urls)))
    try:
        async with context.session.post(API_ENDPOINT, params=params, json=data) as response:
            # print('Status: {}; content type: {}.'.format(response.status, response.content_type))
            if response.status == 201 and response.content_type == 'application/json':
                batch = await response.json()
                print('Batch finished.')
                for job in batch['capture_jobs']:
                    if job['guid'] is None:
                        print(job['message'])
                    else:
                        context.permas[job['submitted_url']] = 'https://perma.cc/{}'.format(job['guid'])
    except asyncio.TimeoutError:
        if len(urls) >= 4:
            print('Splitting...')
            mid = len(urls) // 2
            await asyncio.gather(
                make_permas_batch(context, urls[:mid]),
                make_permas_batch(context, urls[mid:]),
            )

def make_permas_futures(context):
    url_strs_unfiltered = [url.normalized() for url in context.all_urls]

    # Perma is broken for washingtonpost.com for some reason!
    url_strs = [url for url in url_strs_unfiltered if '//perma.cc' not in url and 'washingtonpost.com' not in url]
    print('Making permas for {} URLs.'.format(len(url_strs)))

    return [make_permas_batch(context, chunk) for chunk in chunks(url_strs, API_CHUNK_SIZE)]

class PermaContext(object):
    def __init__(self, all_urls, api_key=None, folder=None, limit=5, timeout=20):
        if folder is None:
            print('No folder supplied!')
            folder = CONFIG['perma']['folder_id']

        if api_key is None:
            print('No API key supplied!')
            api_key = CONFIG['perma']['api_key']

        self.all_urls = all_urls
        self.api_key = api_key
        self.folder = folder

        ssl_context = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl_context=ssl_context, limit=limit)
        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        self.session = aiohttp.ClientSession(connector=connector, timeout=timeout_obj)
        self.permas = {}

    async def __aenter__(self):
        await self.session.__aenter__()
        return self

    async def __aexit__(self, *args):
        return await self.session.__aexit__(*args)

async def make_permas_co(urls, api_key, folder):
    async with PermaContext(urls, api_key=api_key, folder=folder) as context:
        await asyncio.gather(*make_permas_futures(context))
        return context.permas

def make_permas(urls, api_key=None, folder=None):
    return run(make_permas_co(urls, api_key, folder))

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
        url_str = url.normalized()
        if url_str in permas:
            yield url.insert_after(' [{}]'.format(permas[url_str]))

PERMA_RE = re.compile(r'[^A-Za-z0-9]*(https?://)?perma.cc')
def apply_docx(docx):
    footnotes = docx.footnote_list
    urls = list(collect_urls(footnotes))

    permas = make_permas(urls)
    # print(permas)
    insertions = generate_insertions(urls, permas)

    print('Applying insertions.')
    Insertion.apply_all(insertions)

    print('Removing hyperlinks.')
    footnotes.remove_hyperlinks()

def apply_file(file_or_obj, out_filename):
    with Docx(file_or_obj) as docx:
        apply_docx(docx)
        docx.write(out_filename)
