import asyncio
import boto3
from io import BufferedReader
import json
from os.path import join
import tempfile

from footnotes.pull import pull, PullContext, write_spreadsheet

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
    queue_url = bucket_object.metadata['x-amz-meta-queueurl']
    file_uuid = bucket_object.metadata['x-amz-meta-uuid']
    original_name = bucket_object.metadata['x-amz-meta-originalname']
    stream = BufferedReader(body)

    queue = sqs.Queue(queue_url)

    zipfile_path = join(tempfile.gettempdir(), file_uuid + '.zip')
    spreadsheet_path = join(tempfile.gettempdir(), file_uuid + '.xlsx')
    queue.send_message(json.dumps({
        'message': 'start',
        'job_id': job_id,
        'file_uuid': job_uuid,
    }))

    with PullContext(stream, zipfile_path) as context:
        downloads, pull_infos = pull(context)
        tasks = [asyncio.ensure_future(dl) for dl in downloads]
        total = len(tasks)
        pending = tasks
        while len(pending) > 0:
            queue.send_message(json.dumps({
                'message': 'progress',
                'progress': total - len(pending),
                'total': total,
                'job_id': job_id,
                'file_uuid': job_uuid,
            }))
            done, pending = asyncio.wait(pending, timeout=0.2)

        write_spreadsheet(pull_infos, spreadsheet_path)

    out_bucket = s3.bucket('autopull-results')
    out_bucket.upload_file(zipfile_path, 'pull/{}/{}.zip'.format(file_uuid, original_name), ExtraArgs={
        ACL: 'public-read',
        ContentType: 'application/zip',
    })
    out_bucket.upload_file(spreadsheet_path, 'pull/{}/{}.xlsx'.format(file_uuid, original_name), ExtraArgs={
        ACL: 'public-read',
        ContentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })

    queue.send_message(json.dumps({
        'message': 'complete',
        'job_id': job_id,
        'file_uuid': job_uuid,
        'spreadsheet': '',
        'zipfile': '',
    }))

def perma(event, context):
    return ''
