"""
Post-remediation accessibility checker.

Downloads the remediated PDF from S3, runs PDF/UA + WCAG 2.1 AA checks,
and uploads the report to S3.

Replaces Adobe PDFAccessibilityCheckerJob with open-source pikepdf/PyMuPDF checks.
"""

import os
import re
import json
import boto3
from pdf_accessibility_checker import check_accessibility


def download_file_from_s3(bucket_name, file_key, save_path, local_path):
    s3 = boto3.client('s3')
    print(f"Filename : {file_key} | File key in the function: {save_path}")
    s3.download_file(bucket_name, save_path, local_path)
    print(f"Filename : {file_key} | Downloaded {file_key} from {bucket_name} to {local_path}")


def save_report_to_s3(bucket_name, file_key, report):
    s3 = boto3.client('s3')
    file_key_without_extension = os.path.splitext(file_key)[0]
    file_key_without_compliant = file_key_without_extension.replace("COMPLIANT_", "", 1)

    bucket_save_path = f"temp/{file_key_without_compliant}/accessability-report/{file_key_without_extension}_accessibility_report_after_remidiation.json"

    local_path = "/tmp/result_after_remediation.json"
    with open(local_path, "w") as f:
        json.dump(report, f, indent=2)

    with open(local_path, "rb") as data:
        s3.upload_fileobj(data, bucket_name, bucket_save_path)
    print(f"Filename {file_key} | Uploaded report to {bucket_name} at path {bucket_save_path}")
    return bucket_save_path


def lambda_handler(event, context):
    print("Received event:", event)

    payload = event.get('Payload', {})
    body = payload.get('body', {})
    s3_bucket = body.get('bucket')
    save_path = body.get('save_path')

    if not s3_bucket or not save_path:
        raise ValueError("Missing required inputs: 's3_bucket' or 'save_path'")

    print(f"s3_bucket: {s3_bucket}, save_path: {save_path}")

    pattern = r"COMPLIANT_[^/]*"
    match = re.search(pattern, save_path)
    if not match:
        raise ValueError(f"Pattern '{pattern}' not found in save_path: {save_path}")

    file_basename = match.group(0)
    print("File basename:", file_basename)

    local_path = f"/tmp/{file_basename}"
    download_file_from_s3(s3_bucket, file_basename, save_path, local_path)

    try:
        report = check_accessibility(local_path)
        bucket_save_path = save_report_to_s3(s3_bucket, file_basename, report)
        print(f"Filename : {file_basename} | Saved accessibility report to {bucket_save_path}")
        print(f"Filename : {file_basename} | Summary: {report['summary']}")
    except Exception as e:
        print(f'Filename : {file_basename} | Exception encountered: {e}')
        return f"Filename : {file_basename} | Exception encountered: {e}"

    return f"Filename : {file_basename} | Saved accessibility report to {bucket_save_path}"
