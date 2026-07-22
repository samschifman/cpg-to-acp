"""S3-compatible artifact store for large payload transfer between pods.

In distributed mode (ARTIFACT_STORE_URL set), pods store large payloads
(patient bundles, recommendations, FHIR bundles) in MinIO/S3 and pass
references through the SonataFlow workflow. In local mode (no URL set),
get_artifact_store() returns None and services pass data inline.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

_DEFAULT_BUCKET = "cpg-artifacts"


class ArtifactStore:
    """S3-compatible store for pipeline artifacts."""

    def __init__(
        self,
        endpoint_url: str,
        bucket: str = _DEFAULT_BUCKET,
        access_key: str = "minioadmin",
        secret_key: str = "minioadmin",
    ):
        import boto3
        from botocore.config import Config

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )
        self._ensure_bucket()

    def _ensure_bucket(self):
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception:
            try:
                self.client.create_bucket(Bucket=self.bucket)
                logger.info("Created artifact bucket: %s", self.bucket)
            except Exception:
                pass

    def put(self, key: str, data: dict) -> str:
        """Store a JSON artifact. Returns the key for later retrieval."""
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=json.dumps(data).encode(),
            ContentType="application/json",
        )
        logger.debug("Stored artifact: %s/%s", self.bucket, key)
        return key

    def get(self, key: str) -> dict:
        """Fetch a JSON artifact by key."""
        obj = self.client.get_object(Bucket=self.bucket, Key=key)
        data = json.loads(obj["Body"].read().decode())
        logger.debug("Fetched artifact: %s/%s", self.bucket, key)
        return data


def get_artifact_store() -> ArtifactStore | None:
    """Return an ArtifactStore if ARTIFACT_STORE_URL is set, else None.

    When None, services operate in inline mode (local development).
    """
    url = os.environ.get("ARTIFACT_STORE_URL", "")
    if not url:
        return None
    return ArtifactStore(
        endpoint_url=url,
        bucket=os.environ.get("ARTIFACT_STORE_BUCKET", _DEFAULT_BUCKET),
        access_key=os.environ.get("ARTIFACT_STORE_ACCESS_KEY", "minioadmin"),
        secret_key=os.environ.get("ARTIFACT_STORE_SECRET_KEY", "minioadmin"),
    )


def resolve_ref(data: dict, field: str, store: ArtifactStore | None) -> dict | list:
    """Resolve a field that may be inline or a _ref.

    If `{field}_ref` exists in data and store is available, fetch from store.
    Otherwise return data[field] directly.
    """
    ref_key = f"{field}_ref"
    if store and ref_key in data:
        return store.get(data[ref_key])
    return data.get(field, data.get(ref_key, {}))


def store_artifact(
    store: ArtifactStore | None, key: str, data: dict
) -> tuple[dict | None, str | None]:
    """Store data in the artifact store if available.

    Returns (None, ref_key) if stored, or (data, None) if inline.
    """
    if store:
        ref = store.put(key, data)
        return None, ref
    return data, None
