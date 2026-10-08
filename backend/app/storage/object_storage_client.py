"""Object-storage (S3) client construction.

Phase 5 stood the object store up with TLS deliberately ahead of any client
that talks to it, so that the default, easiest-to-write client is also the
compliant one (see docs/SECURITY.md and issue #13).
build_object_storage_client() is the one place that constructs the S3
client - every caller in this codebase must go through it rather than
calling boto3.client directly, so this guarantee can't be quietly bypassed
at a second call site.

boto3 (the vendor-neutral AWS SDK) rather than a storage vendor's own SDK:
the backend speaks only the generic S3 API, so the server behind it
(SeaweedFS today, see issue #94) can change without a client change.
"""

import boto3
from botocore.client import BaseClient
from botocore.config import Config

from app.core.config import settings

# SigV4 needs a region name even though an in-cluster S3 server has no
# regions; every S3-compatible server accepts the AWS default. A fixed
# constant, not a setting: nothing an operator configures depends on it.
_SIGNING_REGION = "us-east-1"


def build_object_storage_client() -> BaseClient:
    """Build the S3 client used for all object storage.

    TLS is decided by object_storage_url's scheme (https:// vs http://), the
    same "let the URL decide" rule every other outbound client in this
    codebase follows (see app.core.tls). The Helm-deployed SeaweedFS (Phase 5)
    is configured with an https:// URL, so the default path there is TLS
    verified against the internal CA bundle - exactly the compliant behaviour
    issue #13 requires. Local dev / docker-compose run object storage over
    plaintext like every other service in that stack and configure http://.
    A bare host:port with no scheme is treated as http://, as it was before.

    TODO(#17): docker-compose's object storage (and the rest of the local
    stack) is planned to move to TLS-by-default; when that lands, the
    http:// case becomes dead code for every environment, not just
    production.

    verify is the internal CA bundle when settings.ca_bundle_path is set,
    otherwise True (the default trust store) - never False: verification
    is only ever narrowed to a specific CA, not disabled.

    Path-style addressing (https://host/bucket/key) is required: an
    in-cluster S3 server reached by a Service name has no per-bucket DNS,
    so virtual-host style (https://bucket.host/key) would never resolve.
    """
    endpoint_url = settings.object_storage_url
    if "//" not in endpoint_url:
        endpoint_url = f"http://{endpoint_url}"

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.object_storage_access_key,
        aws_secret_access_key=settings.object_storage_secret_key,
        region_name=_SIGNING_REGION,
        verify=settings.ca_bundle_path or True,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
