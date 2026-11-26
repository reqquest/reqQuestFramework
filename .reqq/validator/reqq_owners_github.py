# -*- coding: utf-8 -*-
"""
reqq_owners_github.py — GitHub REST client and host probe for rule V6 of reqq_owners.py
(REQQF-ADR-GOV-100 D10, D12). HTTP through `urllib`; plain data, no findings.

Facts from the probe of 2026-11-17 (API version 2026-03-10, same as 2022-11-28):
  - GITHUB_TOKEN always gets 403 from branches/{b}/protection; an admin token gets 200
    or 404 "Branch not protected", also for a branch protected by a ruleset only;
  - rules/branches/{b} returns the rules of active rulesets and is readable by GITHUB_TOKEN;
  - branches/{b} has `protected`: true with classic protection or an active ruleset;
  - codeowners/errors?ref= reports every owner without write access as "Unknown owner";
    for a commit without CODEOWNERS it answers 404 "Not Found" (checked 2026-11-20);
  - a fine-grained token needs Administration: read for branches/{b}/protection and
    Contents: read for branches/{b} and codeowners/errors, which with Administration: read
    alone answer 403 (X-Accepted-GitHub-Permissions, checked 2026-11-20);
  - a token that cannot see a private repository gets 404 "Not Found" from rules/branches/{b}
    and codeowners/errors alike, so a readable rules list proves that a 404 from
    codeowners/errors means no CODEOWNERS at the commit (checked 2026-11-22).
"""
import http.client
import json
import urllib.error
import urllib.request
from typing import Any, NamedTuple

API_VERSION = "2026-03-10"
ENFORCED, NOT_ENFORCED, UNKNOWN = "enforced", "not_enforced", "unknown"


class Response(NamedTuple):
    """An API answer; status 0 = no HTTP response, body None = not JSON."""
    status: int
    body: Any


def _json(data: bytes) -> Any:
    try:
        return json.loads(data)
    except ValueError:
        return None


def api_get(api_url: str, token: str, path: str) -> Response:
    """GET <api_url>/<path>; HTTP errors are answers too, a failed connection or a broken
    HTTP answer is status 0."""
    request = urllib.request.Request(f"{api_url}/{path}", headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "Authorization": f"Bearer {token}",
    })
    try:
        with urllib.request.urlopen(request, timeout=30) as r:
            return Response(r.status, _json(r.read()))
    except urllib.error.HTTPError as e:
        return Response(e.code, _json(e.read()))
    except (OSError, http.client.HTTPException):
        return Response(0, None)


def _readable(r: Response, kind: type) -> bool:
    """A 200 answer whose body has the JSON shape GitHub documents (list or object)."""
    return r.status == 200 and isinstance(r.body, kind)


def sees_repository(rules: Response) -> bool:
    """A readable rules list proves that the token sees the repository (probe of 2026-11-22)."""
    return _readable(rules, list)


def _ruleset_requires(rules: Response) -> bool:
    return _readable(rules, list) and any(
        r["type"] == "pull_request" and r["parameters"].get("require_code_owner_review")
        for r in rules.body)


def _protection_requires(protection: Response) -> bool:
    return _readable(protection, dict) and bool(
        (protection.body.get("required_pull_request_reviews") or {})
        .get("require_code_owner_reviews"))


def _no_classic_requirement(protection: Response, branch: Response) -> bool:
    """Proof that classic branch protection does not require code owner review."""
    return (_readable(protection, dict)
            or (protection.status == 404
                and (protection.body or {}).get("message") == "Branch not protected")
            or (_readable(branch, dict) and branch.body.get("protected") is False))


def probe_verdict(rules: Response, protection: Response, branch: Response) -> str:
    """ENFORCED when a ruleset or the branch protection requires code owner review;
    NOT_ENFORCED when readable sources prove it does not (D11); UNKNOWN otherwise (D10)."""
    if _ruleset_requires(rules) or _protection_requires(protection):
        return ENFORCED
    if _readable(rules, list) and _no_classic_requirement(protection, branch):
        return NOT_ENFORCED
    return UNKNOWN
