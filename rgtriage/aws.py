"""boto3 sessions that can only make read calls.

Every session gets a before-call hook that rejects any operation that is not a
read. This holds even when the underlying credentials are administrator keys.
"""
from __future__ import annotations

import re

import boto3
from botocore.config import Config

READ_PREFIXES = ("Describe", "Get", "List", "BatchGet", "Lookup", "Search")
# Reads that return secrets or customer data rather than configuration.
DENIED = {
    "GetSecretValue", "BatchGetSecretValue", "GetObject", "GetObjectTorrent", "SelectObjectContent",
    "GetParameter", "GetParameters", "GetParametersByPath", "GetPasswordData", "Decrypt",
    "GetCredentialReport", "GenerateCredentialReport", "GetSessionToken", "GetFederationToken",
    "GetAuthorizationToken", "GetLoginProfile", "GetRecords", "GetShardIterator", "GetQueryResults",
    "Scan", "Query", "GetItem", "BatchGetItem", "GetLogEvents", "FilterLogEvents", "GetConsoleOutput",
    "GetConsoleScreenshot", "GetFunction", "GetLayerVersion", "GetTemplate", "GetDataKey",
}
# Non-prefixed reads that are needed. The IAM simulator and Access Analyzer policy checks evaluate policies
# and return a verdict; they change nothing in the account.
ALLOWED_EXTRA = {"AssumeRole", "GetCallerIdentity",
                 "SimulatePrincipalPolicy", "SimulateCustomPolicy",
                 "CheckNoPublicAccess", "CheckAccessNotGranted", "CheckNoNewAccess", "ValidatePolicy"}
# Operations that evaluate rather than read; the desk must say they are evaluations, not observed configuration.
EVALUATIONS = {"SimulatePrincipalPolicy", "SimulateCustomPolicy", "CheckNoPublicAccess", "CheckAccessNotGranted",
               "CheckNoNewAccess", "ValidatePolicy"}

_CONFIG = Config(retries={"max_attempts": 4, "mode": "adaptive"}, connect_timeout=10, read_timeout=30,
                 user_agent_extra="remedigenius-triage")


class WriteBlocked(PermissionError):
    pass


def is_read_operation(name: str) -> bool:
    if name in ALLOWED_EXTRA:
        return True
    if name in DENIED:
        return False
    return name.startswith(READ_PREFIXES)


def _guard(model=None, **_):
    name = getattr(model, "name", "")
    if not is_read_operation(name):
        raise WriteBlocked(f"rgtriage is read-only; refused AWS operation {name}")


def guarded(session: boto3.Session) -> boto3.Session:
    session.events.register("before-call.*.*", _guard)
    return session


def session_for(account: dict, region: str | None = None) -> boto3.Session:
    base = boto3.Session(profile_name=account.get("aws_profile") or None, region_name=region)
    guarded(base)
    role = account.get("role_arn")
    if not role:
        return base
    params = {"RoleArn": role, "RoleSessionName": "remedigenius-triage", "DurationSeconds": 3600}
    if account.get("external_id"):
        params["ExternalId"] = account["external_id"]
    creds = base.client("sts", config=_CONFIG).assume_role(**params)["Credentials"]
    assumed = boto3.Session(aws_access_key_id=creds["AccessKeyId"], aws_secret_access_key=creds["SecretAccessKey"],
                            aws_session_token=creds["SessionToken"], region_name=region)
    return guarded(assumed)


def client(session: boto3.Session, service: str, region: str):
    return session.client(service, region_name=region, config=_CONFIG)


def snake_to_pascal(op: str) -> str:
    if re.fullmatch(r"[a-z0-9_]+", op):
        return "".join(part.capitalize() for part in op.split("_"))
    return op


def error_code(exc: Exception) -> str:
    response = getattr(exc, "response", None) or {}
    return (response.get("Error") or {}).get("Code") or type(exc).__name__
