# -*- coding: utf-8 -*-
"""GitHub access for the toolkit: releases, assets, checksums, payload extraction."""
import hashlib, io, json, os, socket, tarfile
import urllib.error, urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple

import reqq_toolkit_core as T  # noqa: E402


def _parse_github_repo(source_url: str) -> Tuple[str, str]:
    """Parse https://github.com/<owner>/<repo> into (owner, repo)."""
    url = source_url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    parts = url.split("/")
    if len(parts) >= 2 and parts[-1] and parts[-2]:
        return parts[-2], parts[-1]
    raise T.ToolkitError(f"Invalid GitHub URL: {source_url}", code="INVALID_SOURCE_URL")


GITHUB_API_TIMEOUT = 10  # seconds; `ci-notify` runs on every push — never hang a runner


GITHUB_DOWNLOAD_TIMEOUT = 30  # asset payloads only carry the toolkit boundary (a few KB), but


                              # allow for a slow redirect to the CDN
GITHUB_RELEASES_PER_PAGE = 100   # API maximum


GITHUB_RELEASES_MAX_PAGES = 5    # 500 releases is plenty; keeps the CI step bounded


def _github_api_get(endpoint: str) -> Any:
    """Fetch JSON from GitHub API. Supports optional GITHUB_TOKEN from env.

    Returns whatever the endpoint yields — a dict for /releases/latest, a list for /releases.
    """
    url = f"https://api.github.com{endpoint}"
    headers = {"Accept": "application/vnd.github+json"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=GITHUB_API_TIMEOUT) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # Distinct from the catch-all below (reqQuestFramework#7): a 404 is the one HTTP
            # status that unambiguously means "this resource does not exist", as opposed to
            # auth/rate-limit/server trouble (401/403/5xx) that also lands here as
            # GITHUB_API_ERROR. `_fetch_release_by_tag` relies on this to tell "the release
            # was genuinely deleted" apart from "GitHub is unreachable right now" — only the
            # former is safe to treat as a missing merge base and fall back from.
            raise T.ToolkitError(f"GitHub API 404: {e.reason} ({endpoint})", code="GITHUB_API_NOT_FOUND")
        raise T.ToolkitError(f"GitHub API {e.code}: {e.reason}", code="GITHUB_API_ERROR")
    except (socket.timeout, TimeoutError):
        raise T.ToolkitError(f"GitHub API timed out after {GITHUB_API_TIMEOUT}s", code="GITHUB_API_TIMEOUT")
    except urllib.error.URLError as e:
        raise T.ToolkitError(f"Network error: {e.reason}", code="NETWORK_ERROR")
    except json.JSONDecodeError as e:
        raise T.ToolkitError(f"Malformed GitHub API response: {e}", code="GITHUB_API_MALFORMED")


def _iter_releases(owner: str, repo: str):
    """Yield releases newest-first across pages.

    /releases is paginated at 30 by default. With two tag prefixes in play
    (REQQF-ADR-TOOLKIT-100 D1-decision) a run of `docs-v*` releases can push every `toolkit-v*`
    tag off the first page, which would read as "no toolkit release exists". Walks up to
    GITHUB_RELEASES_MAX_PAGES so `ci-notify` stays bounded — it runs on every push.
    """
    for page in range(1, GITHUB_RELEASES_MAX_PAGES + 1):
        batch = _github_api_get(
            f"/repos/{owner}/{repo}/releases"
            f"?per_page={GITHUB_RELEASES_PER_PAGE}&page={page}")
        if not isinstance(batch, list):
            raise T.ToolkitError("Invalid GitHub API response: expected a list of releases",
                                code="GITHUB_API_MALFORMED")
        for rel in batch:
            yield rel
        if len(batch) < GITHUB_RELEASES_PER_PAGE:
            return


def _latest_release_tag(source: str, channel: str) -> str:
    """Get the newest toolkit release tag on `channel`.

    Deliberately does NOT use /releases/latest: that endpoint ignores tag prefixes, so a
    `docs-v*` release (REQQF-ADR-TOOLKIT-100 D1-decision) would be returned as the toolkit version.
    Both channels list /releases and keep only `toolkit-v*` tags.

    channel='stable' → newest non-prerelease; channel='next' → newest of any kind.
    """
    owner, repo = _parse_github_repo(source)

    candidates: List[str] = []
    for rel in _iter_releases(owner, repo):
        tag = (rel or {}).get("tag_name")
        if not tag or not tag.startswith(T.TOOLKIT_TAG_PREFIX):
            continue
        if channel == "stable" and rel.get("prerelease"):
            continue
        try:
            T._semver_tuple(tag)  # skip tags that are not parseable SemVer
        except T.ToolkitError:
            continue
        candidates.append(tag)

    if not candidates:
        raise T.ToolkitError(
            f"No {T.TOOLKIT_TAG_PREFIX}* release found on channel '{channel}' in {owner}/{repo}",
            code="RELEASE_NOT_FOUND")

    newest = candidates[0]
    for tag in candidates[1:]:
        if T._semver_lt(newest, tag):
            newest = tag
    return newest


def _http_get_bytes(url: str) -> bytes:
    """GET raw bytes from an arbitrary URL — used to download a release asset.

    Separate from `_github_api_get`: asset downloads come from a different host (the
    release CDN, after a redirect) and are not JSON. `GITHUB_TOKEN` is forwarded for
    private repos.
    """
    headers = {"Accept": "application/octet-stream"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=GITHUB_DOWNLOAD_TIMEOUT) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        raise T.ToolkitError(f"Download failed — HTTP {e.code} {e.reason}: {url}", code="DOWNLOAD_FAILED")
    except (socket.timeout, TimeoutError):
        raise T.ToolkitError(f"Download timed out after {GITHUB_DOWNLOAD_TIMEOUT}s: {url}",
                                code="DOWNLOAD_TIMEOUT")
    except urllib.error.URLError as e:
        raise T.ToolkitError(f"Network error downloading {url}: {e.reason}", code="NETWORK_ERROR")


def _fetch_release_by_tag(source: str, tag: str) -> Dict[str, Any]:
    """GET /repos/<owner>/<repo>/releases/tags/<tag> → the release object.

    A 404 from the API (`GITHUB_API_NOT_FOUND`) is normalized to `RELEASE_NOT_FOUND` here,
    same as a malformed-but-200 response — both mean "no release for this tag", the case
    `cmd_upgrade`'s missing-base fallback (reqQuestFramework#7) treats as genuinely missing.
    Any other API failure (auth, rate limit, 5xx, timeout, network) propagates unchanged and
    is NOT treated as "missing".
    """
    owner, repo = _parse_github_repo(source)
    try:
        rel = _github_api_get(f"/repos/{owner}/{repo}/releases/tags/{tag}")
    except T.ToolkitError as e:
        if e.code == "GITHUB_API_NOT_FOUND":
            raise T.ToolkitError(f"No release found for tag {tag!r} in {owner}/{repo}",
                                code="RELEASE_NOT_FOUND")
        raise
    if not isinstance(rel, dict) or not rel.get("tag_name"):
        raise T.ToolkitError(f"No release found for tag {tag!r} in {owner}/{repo}", code="RELEASE_NOT_FOUND")
    return rel


def _parse_sha256sums(text: str) -> Dict[str, str]:
    """Parse a coreutils-style `SHA256SUMS` block → {basename: lowercase hexdigest}.

    Per REQQF-ADR-TOOLKIT-100 D4 / D7-decision the sums live in the GitHub Release body
    (no separate signature for now). Non-matching lines are ignored so the block may
    be wrapped in prose or a ``` fence.
    """
    sums: Dict[str, str] = {}
    for line in text.splitlines():
        m = T._SHA256SUMS_RE.match(line.strip())
        if m:
            sums[os.path.basename(m.group(2).strip())] = m.group(1).lower()
    return sums


def _extract_tar_safely(blob: bytes, dest: Path) -> None:
    """Unpack a .tar.gz held in memory into `dest`, rejecting path traversal.

    No member may resolve outside `dest`; only regular files and directories are
    written — symlinks, hardlinks and devices are skipped (the toolkit boundary is
    plain files, D1).
    """
    dest.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest.resolve()
    try:
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
            safe_members = []
            for member in tar.getmembers():
                if not (member.isfile() or member.isdir()):
                    continue
                target = (dest / member.name).resolve()
                if target != dest_resolved and dest_resolved not in target.parents:
                    raise T.ToolkitError(
                        f"Refusing tar member that escapes the destination: {member.name!r}",
                        code="TAR_UNSAFE_MEMBER")
                safe_members.append(member)
            try:
                tar.extractall(dest, members=safe_members, filter="data")
            except TypeError:  # Python < 3.12 has no `filter=`
                tar.extractall(dest, members=safe_members)
    except tarfile.TarError as e:
        raise T.ToolkitError(f"Corrupt toolkit tarball: {e}", code="TAR_CORRUPT")


def _find_payload_root(unpacked: Path) -> Path:
    """The tarball may or may not wrap its contents in a single top-level directory.

    Descend through lone sub-directories until `.reqq/` appears, so the plan sees the
    same layout as the working tree regardless of how #32 packs the asset.
    """
    cur = unpacked
    for _ in range(4):
        if (cur / ".reqq").exists():
            return cur
        if not cur.is_dir():
            break
        children = list(cur.iterdir())
        if len(children) == 1 and children[0].is_dir():
            cur = children[0]
            continue
        break
    return unpacked


def _validate_offline_payload_dir(raw: str, flag: str) -> Path:
    """Validate a `--base-payload`/`--target-payload` directory before it is trusted as a
    release payload, and return its resolved payload root.

    `_find_payload_root` does not check existence — a missing, empty, or mistyped directory
    resolves right back to itself with no error. Fed straight into `_compute_upgrade_plan`,
    that reads as "the target release removed every boundary file": every unchanged local
    file gets a REMOVE action, the adopter's tree gets emptied, and `toolkit.lock` still
    advances to the requested version with exit 0 — a silent data-loss path from a plain
    typo (reqQuestFramework#3 review). Requiring `.reqq/` under the resolved root — the same
    marker `_find_payload_root` itself searches for — catches a missing directory, an empty
    one, a path to a plain file, and a directory that just isn't a toolkit payload.
    """
    p = Path(raw)
    if not p.is_dir():
        raise T.ToolkitError(f"{flag} {raw!r} is not an existing directory", code="PAYLOAD_INVALID")
    root = _find_payload_root(p)
    if not (root / ".reqq").is_dir():
        raise T.ToolkitError(
            f"{flag} {raw!r} does not look like an extracted toolkit payload "
            f"(no .reqq/ found under {root})", code="PAYLOAD_INVALID")
    return root


def _download_toolkit_payload(source: str, tag: str, dest: Path) -> Path:
    """Download, checksum-verify and unpack the `raac-toolkit-*.tar.gz` for `tag`.

    Verification is mandatory: the SHA256 of the asset must match its entry in the
    release body's `SHA256SUMS` block. A missing or mismatched sum aborts the upgrade
    rather than merging from an unverifiable payload. Returns the payload root.
    """
    version = T._normalize_version(tag)
    asset_name = T.TOOLKIT_ASSET_TEMPLATE.format(version=version)
    rel = _fetch_release_by_tag(source, tag)

    asset_url = None
    for asset in rel.get("assets") or []:
        if asset.get("name") == asset_name:
            asset_url = asset.get("browser_download_url")
            break
    if not asset_url:
        present = [a.get("name") for a in rel.get("assets") or []]
        raise T.ToolkitError(f"Release {tag} has no asset named {asset_name!r} (assets: {present})",
                            code="ASSET_MISSING")

    expected = _parse_sha256sums(rel.get("body") or "").get(asset_name)
    if not expected:
        raise T.ToolkitError(
            f"Release {tag} body has no SHA256SUMS entry for {asset_name} — "
            f"refusing to upgrade from an unverifiable payload", code="CHECKSUM_MISSING")

    blob = _http_get_bytes(asset_url)
    actual = hashlib.sha256(blob).hexdigest()
    if actual != expected:
        raise T.ToolkitError(
            f"Checksum mismatch for {asset_name}: expected {expected}, got {actual}",
            code="CHECKSUM_MISMATCH")

    _extract_tar_safely(blob, dest)
    return _find_payload_root(dest)


def _changelog_delta(source: str, channel: str, from_version: str, to_version: str) -> str:
    """Concatenate release notes for every toolkit release in the range (from, to].

    Best effort: any API problem yields a short pointer instead of failing the upgrade —
    the delta is documentation for the PR body (D6), not a gate.
    """
    try:
        owner, repo = _parse_github_repo(source)
        picked: List[Tuple[str, str]] = []
        for rel in _iter_releases(owner, repo):
            tag = (rel or {}).get("tag_name") or ""
            if not tag.startswith(T.TOOLKIT_TAG_PREFIX):
                continue
            if channel == "stable" and rel.get("prerelease"):
                continue
            try:
                v = T._normalize_version(tag)
                T._semver_tuple(v)  # skip tags that are not parseable SemVer
            except T.ToolkitError:
                continue
            if T._semver_lt(from_version, v) and not T._semver_lt(to_version, v):
                picked.append((v, (rel.get("body") or "").strip()))
        if not picked:
            return f"(no release notes found for v{from_version}..v{to_version})"
        picked.sort(key=lambda t: T._semver_key(t[0]))
        return "\n\n".join(f"### v{v}\n\n{body or '(no notes)'}" for v, body in picked)
    except T.ToolkitError as e:
        return f"(changelog delta unavailable: {e})"
