import asyncio
import boto3
from io import BytesIO
import json
import os
from os.path import join
import tempfile
from urllib.parse import unquote
import random

from footnotes.footnotes import Docx
from footnotes.perma import collect_urls, generate_insertions, make_permas_futures, PermaContext
from footnotes.pull import add_pullers, pull as pull_sources, PullContext, write_spreadsheet
from footnotes.text import Insertion

async def track_tasks(job_context, futures, last_skip=0, check=lambda: True):
    total = len(futures)
    pending = futures
    while len(pending) > last_skip and check():
        job_context.queue.send_message(MessageBody=json.dumps({
            'message': 'progress',
            'progress': total - len(pending),
            'total': max(len(pending), total - last_skip),
            'job_id': job_context.job_id,
            'file_uuid': job_context.file_uuid,
        }))
        done, pending = await asyncio.wait(pending, timeout=0.2)

    return pending

class JobContext(object):
    def __init__(self, event):
        self.event = event

        self.s3 = boto3.resource('s3')
        self.sqs = boto3.resource('sqs')

        s3_info = self.event['Records'][0]['s3']
        bucket_name = s3_info['bucket']['name']
        object_key = s3_info['object']['key']

        self.bucket = self.s3.Bucket(bucket_name)
        bucket_object = self.bucket.Object(object_key)
        body = bucket_object.get()['Body']
        self.metadata = bucket_object.metadata

        self.queue_url = self.metadata['queue-url']
        self.file_uuid = self.metadata['uuid']
        self.job_id = self.metadata['job-id']
        self.original_name = self.metadata['original-name']

        if self.original_name.endswith('.docx'):
            self.original_name = self.original_name[:-5]

        self.queue = self.sqs.Queue(self.queue_url)

        self.queue.send_message(MessageBody=json.dumps({
            'message': 'start',
            'job_id': self.job_id,
            'file_uuid': self.file_uuid,
        }))

        self.stream = BytesIO(body.read())

    def temp_path(self, extension):
        return join(tempfile.gettempdir(), self.file_uuid + extension)

    def upload_file(self, path, bucket_key, content_type):
        print('Uploading file...')
        out_bucket_name = os.getenv('RESULTS_BUCKET', 'autopull-results')
        out_bucket = self.s3.Bucket(out_bucket_name)
        out_bucket.upload_file(path, bucket_key, ExtraArgs={
            'ACL': 'public-read',
            'ContentType': content_type,
        })

        self.queue.send_message(MessageBody=json.dumps({
            'message': 'complete',
            'result_url': 'https://s3.amazonaws.com/{}/{}'.format(out_bucket_name, bucket_key),
            'queue_url': self.queue_url,
            'job_id': self.job_id,
            'file_uuid': self.file_uuid,
        }))

# Upload from s3 triggers event.
# Download s3 object into ram.
# Build zipfile and xlsx in /tmp.
# Upload zipfile and xlsx to s3.
async def pull_co(event, lambda_context):
    print(event)
    job_context = JobContext(event)

    pullers = None
    if 'pullers' in job_context.metadata:
        pullers_decoded = unquote(job_context.metadata['pullers']).splitlines()
        pullers = [p for p in pullers_decoded if p]
        random.shuffle(pullers)

    zipfile_path = job_context.temp_path('.zip')
    spreadsheet_path = job_context.temp_path('.xlsx')

    zipfile_name = 'Bookpull.{}'.format(job_context.original_name)

    async with PullContext(job_context.stream, zipfile_path, zipfile_prefix=zipfile_name) as context:
        downloads, pull_infos = pull_sources(context)
        def check():
            return (lambda_context.get_remaining_time_in_millis() > 10 * 1000 and
                    context.compressed_size() < 400 * 1024 * 1024)
        await track_tasks(job_context, downloads, last_skip=5, check=check)

        if pullers:
            add_pullers(pull_infos, pullers)

        write_spreadsheet(pull_infos, spreadsheet_path)
        context.zipf.write(spreadsheet_path, '{}/0.Bookpull.{}.xlsx'.format(
            context.zipfile_prefix,
            job_context.original_name
        ))
        os.remove(spreadsheet_path)

    bucket_key = 'pull/{}/{}.zip'.format(job_context.file_uuid, zipfile_name)
    job_context.upload_file(zipfile_path, bucket_key, 'application/zip')
    os.remove(zipfile_path)

def pull(event, context):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(pull_co(event, context))

async def perma_co(event, lambda_context):
    print(event)
    job_context = JobContext(event)

    perma_api_key = job_context.metadata.get('perma-api')
    perma_folder = job_context.metadata.get('perma-folder')

    out_path = job_context.temp_path('.docx')

    with Docx(job_context.stream) as docx:
        footnotes = docx.footnote_list
        urls = list(collect_urls(footnotes))

        async with PermaContext(urls, api_key=perma_api_key, folder=perma_folder) as perma_context:
            futures = make_permas_futures(perma_context)
            def check():
                return lambda_context.get_remaining_time_in_millis() > 10 * 1000
            await track_tasks(job_context, futures, check=check)

            insertions = generate_insertions(urls, perma_context.permas)

        print('Applying insertions.')
        Insertion.apply_all(insertions)

        print('Removing hyperlinks.')
        footnotes.remove_hyperlinks()

        docx.write(out_path)

    print('Uploading docx...')
    bucket_key = 'perma/{}/{}_perma.docx'.format(job_context.file_uuid, job_context.original_name)
    job_context.upload_file(out_path, bucket_key, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    os.remove(out_path)

def perma(event, context):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(perma_co(event, context))
