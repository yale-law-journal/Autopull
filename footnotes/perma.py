import aiohttp
import asyncio
import json
from os.path import dirname, join
import sys

from .config import CONFIG

API_ENDPOINT = 'https://api.perma.cc/v1/archives/batches'
API_CHUNK_SIZE = 10

def run(coroutine):
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(coroutine)
    loop.close()
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

async def make_permas_co(urls, folder):
    print('Making permas for {} URLs.'.format(len(urls)))
    async with aiohttp.ClientSession() as session:
        if folder is None:
            folder = CONFIG['perma']['folder_id']

        batches = []
        result = {}
        for chunk in chunks(urls, API_CHUNK_SIZE):
            await make_permas_batch(session, chunk, folder, result)

        return result

def make_permas(urls, folder=None):
    return run(make_permas_co(urls, folder))
