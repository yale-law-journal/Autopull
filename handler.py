import asyncio
import boto3
from io import BytesIO
import json
import os
from os.path import join
import tempfile

from footnotes.pull import pull as pull_sources, PullContext, write_spreadsheet

# Upload from s3 triggers event.
# Download s3 object into ram.
# Build zipfile and xlsx in /tmp.
# Upload zipfile and xlsx to s3.
def pull(event, context):
    print(event)
    s3 = boto3.resource('s3')
    sqs = boto3.resource('sqs')

    s3_info = event['Records'][0]['s3']
    bucket_name = s3_info['bucket']['name']
    object_key = s3_info['object']['key']

    bucket = s3.Bucket(bucket_name)
    bucket_object = bucket.Object(object_key)
    body = bucket_object.get()['Body']
    print(bucket_object.metadata)
    queue_url = bucket_object.metadata['queue-url']
    file_uuid = bucket_object.metadata['uuid']
    original_name = bucket_object.metadata['original-name']
    if original_name.endswith('.docx'):
        original_name = original_name[:-5]
    stream = BytesIO(body.read())

    queue = sqs.Queue(queue_url)

    zipfile_path = join(tempfile.gettempdir(), file_uuid + '.zip')
    spreadsheet_path = join(tempfile.gettempdir(), file_uuid + '.xlsx')
    queue.send_message(MessageBody=json.dumps({
        'message': 'start',
        'file_uuid': file_uuid,
    }))

    with PullContext(stream, zipfile_path) as context:
        downloads, pull_infos = pull_sources(context)
        tasks = [asyncio.ensure_future(dl) for dl in downloads]
        total = len(tasks)
        pending = tasks
        loop = asyncio.get_event_loop()
        while len(pending) > 10:
            queue.send_message(MessageBody=json.dumps({
                'message': 'progress',
                'progress': total - len(pending),
                'total': total,
                'file_uuid': file_uuid,
            }))
            done, pending = loop.run_until_complete(asyncio.wait(pending, timeout=0.2))

        write_spreadsheet(pull_infos, spreadsheet_path)
        context.zipf.write(spreadsheet_path, '{}/0.Bookpull.{}.xlsx'.format(context.zipfile_prefix, original_name))
        os.remove(spreadsheet_path)

    out_bucket = s3.Bucket('autopull-results')
    print('Uploading zip...')
    bucket_zipfile_path = 'pull/{}/Bookpull.{}.zip'.format(file_uuid, original_name)
    out_bucket.upload_file(zipfile_path, bucket_zipfile_path, ExtraArgs={
        'ACL': 'public-read',
        'ContentType': 'application/zip',
    })
    os.remove(zipfile_path)

    queue.send_message(MessageBody=json.dumps({
        'message': 'complete',
        'file_uuid': file_uuid,
        'result_url': 'https://s3.amazonaws.com/autopull-results/' + bucket_zipfile_path,
    }))

def perma(event, context):
    return ''