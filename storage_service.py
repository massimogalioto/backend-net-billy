"""Small, central S3-compatible storage adapter for original CTE PDFs."""
import os
import uuid

import boto3

from database_service import ConfigurationError, default_tenant_id


def _client():
    required = ("S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "S3_ENDPOINT", "S3_REGION")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise ConfigurationError("Configurazione Bucket mancante: " + ", ".join(missing))
    return boto3.client("s3", endpoint_url=os.environ["S3_ENDPOINT"], region_name=os.environ["S3_REGION"],
                        aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
                        aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"])


def upload_cte_pdf(content: bytes, filename: str, content_type: str = "application/pdf") -> dict:
    tenant_id = default_tenant_id()
    object_key = f"tenants/{tenant_id}/cte/{uuid.uuid4()}.pdf"
    _client().put_object(Bucket=os.environ["S3_BUCKET"], Key=object_key, Body=content, ContentType=content_type)
    return {"object_key": object_key, "filename": filename, "content_type": content_type, "size_bytes": len(content)}


def get_pdf(object_key: str):
    return _client().get_object(Bucket=os.environ["S3_BUCKET"], Key=object_key)["Body"].read()


def delete_pdf(object_key: str) -> None:
    _client().delete_object(Bucket=os.environ["S3_BUCKET"], Key=object_key)
