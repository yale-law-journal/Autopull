import aiohttp
import asyncio
import json
from os.path import join
import sys

API_ENDPOINT = 'https://api.perma.cc/v1/archives/batches'
API_CHUNK_SIZE = 10

try:
    with open(join(sys.path[0], 'config.json')) as config_f:
        CONFIG = json.load(config_f)['perma']
except FileNotFoundError:
    with open('config.json') as config_f:
        CONFIG = json.load(config_f)['perma']

def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i + n]

async def make_permas_batch(session, urls, folder, result):
    data = { 'urls': urls, 'target_folder': folder }
    params = { 'api_key': CONFIG['api_key'] }

    print('Starting batch of {}...'.format(len(urls)))
    for _ in range(3):
        async with session.post(API_ENDPOINT, params=params, json=data) as response:
            print('Status: {}; content type: {}.'.format(response.status, response.content_type))
            if response.status == 201 and response.content_type == 'application/json':
                batch = await response.json()
                print('Batch finished.')
                print(json.dumps(batch, indent=4, sort_keys=True))
                for job in batch['capture_jobs']:
                    result[job['submitted_url']] = 'https://perma.cc/{}'.format(job['guid'])

                return

        print('Retrying...')

async def make_permas_co(urls, folder):
    print('Making permas for {} URLs.'.format(len(urls)))
    async with aiohttp.ClientSession() as session:
        if folder is None:
            folder = CONFIG['folder_id']

        batches = []
        result = {}
        for chunk in chunks(urls, API_CHUNK_SIZE):
            await make_permas_batch(session, chunk, folder, result)

        return result

def make_permas(urls, folder=None):
    return asyncio.run(make_permas_co(urls, folder))
