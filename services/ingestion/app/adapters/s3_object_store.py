"""Concrete ObjectStore adapter backed by MinIO (S3-compatible).

This is the only file in the service allowed to import boto3/aioboto3.
"""
import aioboto3


class S3ObjectStore:
    def __init__(self, endpoint_url: str, access_key: str, secret_key: str, bucket: str):
        self._endpoint_url = f"http://{endpoint_url}"
        self._access_key = access_key
        self._secret_key = secret_key
        self._bucket = bucket
        self._session = aioboto3.Session()

    async def ensure_bucket(self) -> None:
        async with self._session.client(
            "s3",
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
        ) as s3:
            try:
                await s3.head_bucket(Bucket=self._bucket)
            except Exception:
                await s3.create_bucket(Bucket=self._bucket)

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        async with self._session.client(
            "s3",
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
        ) as s3:
            await s3.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)
