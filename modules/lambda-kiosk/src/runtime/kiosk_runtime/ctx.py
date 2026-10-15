"""The `ctx` handed to every function: deadline, outputs, logs, AWS clients."""
import json
import os
import re
import time

_SECRETS = [
    re.compile(r"\b(AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(-----END [A-Z ]*PRIVATE KEY-----|$)"),
    re.compile(r"(?i)(aws_secret_access_key|password|secret|token)\s*[=:]\s*\S+"),
]
_NAME_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


def redact(text):
    text = str(text)
    for p in _SECRETS:
        text = p.sub("[REDACTED]", text)
    return text


class S3Writer:
    """Writes under outputs/<agent>/<function>/<run_id>/<unit_index>/ in the kiosk bucket."""

    def __init__(self, bucket, prefix):
        self.bucket, self.prefix, self._s3 = bucket, prefix, None

    def _client(self):
        if self._s3 is None:
            import boto3
            from botocore.config import Config
            self._s3 = boto3.client("s3", config=Config(retries={"mode": "adaptive", "total_max_attempts": 5}))
        return self._s3

    def put(self, name, body, content_type):
        key = self.prefix + name
        self._client().put_object(Bucket=self.bucket, Key=key, Body=body, ContentType=content_type)
        return key

    def get(self, key):
        return self._client().get_object(Bucket=self.bucket, Key=key)["Body"].read()


class MemoryWriter:
    """Test double: keeps outputs in `files` (key -> bytes)."""

    def __init__(self, prefix="outputs/test/fn/test/"):
        self.prefix, self.files = prefix, {}

    def put(self, name, body, content_type):
        key = self.prefix + name
        self.files[key] = body
        return key

    def get(self, key):
        return self.files[key]


class Ctx:
    def __init__(self, writer, deadline, run_id="adhoc", agent="", function="", version="", unit_index=0):
        self.writer, self.deadline, self.run_id, self.unit_index = writer, deadline, run_id, unit_index
        self.agent, self.function, self.version = agent, function, version
        self.outputs = []

    @classmethod
    def from_lambda(cls, context, run_id, unit_index=0):
        # one prefix per unit: units of one run never overwrite each other's outputs
        agent, function = os.environ.get("KIOSK_AGENT", ""), os.environ.get("KIOSK_FUNCTION", "")
        prefix = f"outputs/{agent}/{function}/{run_id}/{unit_index}/"
        return cls(S3Writer(os.environ.get("KIOSK_BUCKET", ""), prefix),
                   time.time() + context.get_remaining_time_in_millis() / 1000.0,
                   run_id, agent, function, os.environ.get("KIOSK_VERSION", ""), unit_index)

    # ---- time
    def remaining_s(self):
        return max(0.0, self.deadline - time.time())

    def should_stop(self, margin_s=30):
        """True when less than margin_s seconds are left: save progress and return PARTIAL."""
        return self.remaining_s() < margin_s

    # ---- outputs (only under this function's own prefix)
    def write_json(self, name, obj):
        return self._put(name, json.dumps(obj, indent=1, default=str).encode("utf-8"), "application/json")

    def write_text(self, name, text):
        return self._put(name, str(text).encode("utf-8"), "text/plain")

    def _put(self, name, body, content_type):
        if not _NAME_OK.match(name or ""):
            raise ValueError(f"output name {name!r}: use letters, digits, dot, dash, underscore (max 100)")
        key = self.writer.put(name, body, content_type)
        self.outputs.append(key)
        return key

    def read_json(self, key):
        """Read an earlier output of the same agent (outputs/<agent>/...)."""
        if not key.startswith(f"outputs/{self.agent}/"):
            raise PermissionError(f"{key}: functions may read only outputs/{self.agent}/...")
        return json.loads(self.writer.get(key))

    # ---- logs (JSON lines, secrets redacted)
    def log(self, msg, **fields):
        rec = {"msg": redact(msg), "run_id": self.run_id}
        rec.update({k: redact(v) for k, v in fields.items()})
        print(json.dumps(rec, default=str))

    # ---- AWS (rights come from the function's class role, nothing else)
    def aws(self, service, region=None):
        import boto3
        from botocore.config import Config
        return boto3.client(service, region_name=region,
                            config=Config(retries={"mode": "adaptive", "total_max_attempts": 8}))
