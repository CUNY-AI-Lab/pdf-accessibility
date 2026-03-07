"""
Pre-remediation accessibility checker.

Downloads the original PDF from S3, runs PDF/UA + WCAG 2.1 AA checks,
and uploads the report to S3.

Replaces Adobe PDFAccessibilityCheckerJob with open-source pikepdf/PyMuPDF checks.
"""

import os
import json
import boto3
from pdf_accessibility_checker import check_accessibility


def download_file_from_s3(bucket_name, file_key, local_path):
    s3 = boto3.client('s3')
    print(f"Filename : {file_key} | File key in the function: {file_key}")
    s3.download_file(bucket_name, f"pdf/{file_key}", local_path)
    print(f"Filename : {file_key} | Downloaded {file_key} from {bucket_name} to {local_path}")


def save_report_to_s3(bucket_name, file_key, report):
    s3 = boto3.client('s3')
    file_key_without_extension = os.path.splitext(file_key)[0]
    bucket_save_path = f"temp/{file_key_without_extension}/accessability-report/{file_key_without_extension}_accessibility_report_before_remidiation.json"

    local_path = "/tmp/result_before_remediation.json"
    with open(local_path, "w") as f:
        json.dump(report, f, indent=2)

    with open(local_path, "rb") as data:
        s3.upload_fileobj(data, bucket_name, bucket_save_path)
    print(f"Filename {file_key} | Uploaded report to {bucket_name} at path {bucket_save_path}")
    return bucket_save_path


def lambda_handler(event, context):
    print("Received event:", event)
    s3_bucket = event.get('s3_bucket', None)
    chunks = event.get('chunks', [])

    if chunks:
        first_chunk = chunks[0]
        s3_key = first_chunk.get('s3_key', None)
        if s3_key:
            file_basename = os.path.basename(s3_key)
            file_basename = file_basename.split("_chunk_")[0] + os.path.splitext(file_basename)[1]

    print("File basename:", file_basename)
    print("s3_bucket:", s3_bucket)
    local_path = f"/tmp/{file_basename}"
    download_file_from_s3(s3_bucket, file_basename, local_path)

    try:
        report = check_accessibility(local_path)
        bucket_save_path = save_report_to_s3(s3_bucket, file_basename, report)
        print(f"Filename : {file_basename} | Saved accessibility report to {bucket_save_path}")
        print(f"Filename : {file_basename} | Summary: {report.get('Summary', report.get('summary', 'N/A'))}")
    except Exception as e:
        print(f'Filename : {file_basename} | Exception encountered: {e}')
        return f"Filename : {file_basename} | Exception encountered: {e}"

    return f"Filename : {file_basename} | Saved accessibility report to {bucket_save_path}"
