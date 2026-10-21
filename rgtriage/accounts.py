"""Account onboarding: find the accounts this desk should cover and how far it can read each one.

Runs before every scan, so onboarding needs no restart and no redeploy:

1. Organization: which organization the desk's account belongs to (any member may ask).
2. Delegated administrator: whether a configured account is the Security Hub / GuardDuty / Inspector
   administrator. Its member lists name the accounts it already sees findings for.
3. Candidates: organization accounts (when the identity may list them) plus those member lists.
4. Probe: try the common read-only role (RemediGeniusReadOnly) in each candidate. An account where it works
   is read from this scan on; one where it does not stays "findings only" (or not covered) and the
   onboarding report says exactly what to deploy.

Everything here is a read; probes are sts:AssumeRole, which the read-only guard allows.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from botocore.exceptions import BotoCoreError, ClientError

from . import aws

ADMIN_SERVICES = ("securityhub", "guardduty", "inspector")
PROBE_LIMIT = 500


def _members(session, service: str, region: str) -> list[str]:
    """Account ids this identity administers for one service (empty when it is not the administrator)."""
    if service == "securityhub":
        c = aws.client(session, "securityhub", region)
        pages = c.get_paginator("list_members").paginate(OnlyAssociated=True)
        return [m["AccountId"] for page in pages for m in page.get("Members", [])]
    if service == "guardduty":
        c = aws.client(session, "guardduty", region)
        ids = []
        for detector in c.list_detectors().get("DetectorIds", [])[:1]:
            pages = c.get_paginator("list_members").paginate(DetectorId=detector, OnlyAssociated="true")
            ids += [m["AccountId"] for page in pages for m in page.get("Members", [])]
        return ids
    c = aws.client(session, "inspector2", region)
    pages = c.get_paginator("list_members").paginate(onlyAssociated=True)
    return [m["accountId"] for page in pages for m in page.get("members", [])
            if m.get("relationshipStatus") in (None, "ENABLED", "CREATED")]


def reader_arn(session) -> str:
    """The identity that assumes member roles, as the ARN a trust policy must name.

    An assumed-role session reports arn:aws:sts::ACCOUNT:assumed-role/NAME/SESSION; the trust policy needs the role's
    IAM ARN including its path (IAM Identity Center roles live under /aws-reserved/sso.amazonaws.com/).
    """
    arn = session.client("sts").get_caller_identity()["Arn"]
    parts = arn.split(":")
    if len(parts) == 6 and parts[2] == "sts" and parts[5].startswith("assumed-role/"):
        name = parts[5].split("/")[1]
        try:
            return session.client("iam").get_role(RoleName=name)["Role"]["Arn"]
        except (ClientError, BotoCoreError):
            return f"arn:aws:iam::{parts[4]}:role/{name}"
    return arn


def _probe(account_id: str, role_name: str, profile_name: str | None = None):
    try:
        session = aws.session_for({"role_arn": f"arn:aws:iam::{account_id}:role/{role_name}", "aws_profile": profile_name})
        return account_id, "ok", "", session
    except ClientError as exc:
        return account_id, "no_role", aws.error_code(exc), None
    except BotoCoreError as exc:
        return account_id, "error", str(exc)[:160], None


def discover(profile: dict, previous: dict | None = None, probe=_probe) -> dict:
    """Add readable organization accounts to profile["accounts"] (in memory) and return the onboarding report.

    The first account in triage.yaml is the desk's own account. Member roles are assumed by the identity
    behind it (the instance role on Spot, your profile on a workstation), never by its read role.
    """
    org = profile["organization"]
    role_name = org["member_role_name"]
    configured = list(profile["accounts"])
    report = {"mode": "standalone", "organization_id": "", "management_account": "", "member_role_name": role_name,
              "reader_arn": "", "account_list": "", "admin": {}, "known_accounts": 0, "full_read": [],
              "findings_only": [], "not_covered": [], "newly_readable": [], "notes": []}
    if not configured:
        return report
    primary = configured[0]
    try:
        session = aws.session_for(primary)
        reader = aws.session_for({"aws_profile": primary.get("aws_profile")})
        report["reader_arn"] = reader_arn(reader)
        primary["account_id"] = primary.get("account_id") or session.client("sts").get_caller_identity()["Account"]
    except (ClientError, BotoCoreError) as exc:
        report["notes"].append(f"cannot authenticate the primary account: {aws.error_code(exc)}")
        return report
    names: dict[str, str] = {}
    orgs = session.client("organizations")
    try:
        info = orgs.describe_organization()["Organization"]
        report.update(mode="organization", organization_id=info["Id"], management_account=info.get("MasterAccountId", ""))
        try:
            pages = orgs.get_paginator("list_accounts").paginate()
            names = {a["Id"]: a["Name"] for page in pages for a in page["Accounts"] if a.get("Status", "ACTIVE") == "ACTIVE"}
            report["account_list"] = "organization"
        except ClientError:
            report["account_list"] = "admin_members"  # only the management account or an Organizations admin may list
    except ClientError as exc:
        if aws.error_code(exc) != "AWSOrganizationsNotInUseException":
            report["notes"].append(f"organization not readable ({aws.error_code(exc)})")
    except BotoCoreError as exc:
        report["notes"].append(f"organization not readable ({str(exc)[:120]})")
    for service in ADMIN_SERVICES:
        try:
            ids = sorted(set(_members(session, service, primary["regions"][0])) - {primary["account_id"]})
        except (ClientError, BotoCoreError):
            continue
        if ids:
            report["admin"][service] = ids
            for i in ids:
                names.setdefault(i, "")
    if "inspector" in report["admin"] and "delegated_admin" not in primary:
        primary["delegated_admin"] = True  # org-wide Inspector totals; detected, no setting needed
    configured_ids = {str(a.get("account_id")) for a in configured if a.get("account_id")}
    candidates = sorted(set(names) - configured_ids - {primary["account_id"]})
    report["known_accounts"] = len((set(names) | configured_ids) - {""})
    results = []
    if candidates and org["discover"] and report["mode"] == "organization":
        with ThreadPoolExecutor(max_workers=16) as pool:
            results = list(pool.map(lambda i: probe(i, role_name, primary.get("aws_profile")), candidates[:PROBE_LIMIT]))
        if len(candidates) > PROBE_LIMIT:
            report["notes"].append(f"{len(candidates) - PROBE_LIMIT} accounts not probed this scan (limit {PROBE_LIMIT})")
    else:
        report["not_covered"] = [i for i in candidates if i not in set().union(*report["admin"].values())]
        report["findings_only"] = [i for i in candidates if i not in report["not_covered"]]
    admin_seen = set().union(*report["admin"].values())
    before = set((previous or {}).get("full_read") or [])
    full = set(configured_ids)
    for account_id, status, _note, member_session in results:
        if status == "ok":
            name = (names.get(account_id) or f"account-{account_id}").lower().replace(" ", "-")
            profile["accounts"].append({"name": name, "account_id": account_id, "regions": profile["regions"],
                                        "role_arn": f"arn:aws:iam::{account_id}:role/{role_name}",
                                        "aws_profile": primary.get("aws_profile"), "criticality": org["criticality"],
                                        "discovered": True, "_session": member_session})
            full.add(account_id)
            if previous is not None and account_id not in before:
                report["newly_readable"].append(account_id)
        else:
            report["findings_only" if account_id in admin_seen else "not_covered"].append(account_id)
    report["full_read"] = sorted(full)
    return report


def skip_pairs(report: dict) -> set[tuple[str, str]]:
    """(source, account) reads to skip: the administrator's view already returns those members' findings,
    so reading them again in the member account would only duplicate them."""
    return {(service, account_id) for service, ids in (report.get("admin") or {}).items() for account_id in ids}


def next_steps(report: dict) -> list[str]:
    """Plain instructions, filled with this environment's values, for the accounts the desk cannot read yet."""
    steps = []
    missing = report["findings_only"] + report["not_covered"]
    role = report["member_role_name"]
    if report["mode"] == "standalone":
        steps.append(f"This account is not in an AWS Organization. To cover another account, deploy "
                     f"deploy/aws-single/member-read-role.yaml there (TrustedPrincipalArn={report['reader_arn']}, "
                     "leave OrganizationId empty) "
                     "and add it under `accounts:` in triage.yaml with its role_arn.")
        return steps
    if not report["admin"]:
        steps.append("This account is not the Security Hub / GuardDuty / Inspector delegated administrator, so other "
                     "accounts' findings arrive only through their read roles. Running the desk in the delegated "
                     "administrator account gives the org-wide findings view with no extra roles.")
    if missing or report.get("account_list") != "organization":
        steps.append(
            f"Give the desk a read role in every account. With management-account (or StackSets delegated "
            f"administrator) credentials, from the RemediGenius-CE release folder, deploy it as a service-managed "
            f"StackSet with auto-deployment:\n"
            f"  aws cloudformation create-stack-set --stack-set-name remedigenius-ce-read "
            f"--template-body file://deploy/aws-single/member-read-role.yaml --permission-model SERVICE_MANAGED "
            f"--auto-deployment Enabled=true,RetainStacksOnAccountRemoval=false --capabilities CAPABILITY_NAMED_IAM "
            f"--parameters ParameterKey=TrustedPrincipalArn,ParameterValue={report['reader_arn']} "
            f"ParameterKey=OrganizationId,ParameterValue={report['organization_id']}\n"
            f"  aws cloudformation create-stack-instances --stack-set-name remedigenius-ce-read "
            f"--deployment-targets OrganizationalUnitIds=<root-or-ou-id> --regions <one-region>\n"
            f"Nothing else is needed: the next scan finds every account where {role} can be assumed, and accounts "
            f"added to the organization later get the role automatically. StackSets do not deploy to the management "
            f"account itself; deploy the template there as a normal stack if it should be covered.")
    if report.get("account_list") == "admin_members":
        steps.append("This identity cannot list the organization's accounts, so only accounts known from the "
                     "delegated-administrator member lists or triage.yaml are probed. List others under `accounts:` "
                     "(account_id is enough when they have the read role), or allow organizations:ListAccounts.")
    return steps


def summary_lines(report: dict) -> list[str]:
    """Board lines: how many accounts are covered and how. Silent for a single standalone account."""
    if not report:
        return []
    if report.get("mode") == "unknown":
        return [f"Accounts: {'; '.join(report.get('notes') or ['discovery did not run'])}"]
    full, partial, none = report.get("full_read") or [], report.get("findings_only") or [], report.get("not_covered") or []
    if report.get("mode") == "standalone" and len(full) <= 1:
        return []
    role = report.get("member_role_name", "RemediGeniusReadOnly")
    lines = [f"Accounts: {len(full)} read fully · {len(partial)} findings only (delegated-admin view, no {role} role) · "
             f"{len(none)} not covered · delegated administrator for: {', '.join(report.get('admin') or {}) or 'none'}."]
    if report.get("newly_readable"):
        lines.append(f"Newly onboarded this scan: {', '.join(report['newly_readable'][:10])} "
                     "(existing findings taken as the baseline).")
    if partial or none:
        lines.append("To read every account fully, ask me to walk through onboarding (`rgtriage onboarding`).")
    return lines
