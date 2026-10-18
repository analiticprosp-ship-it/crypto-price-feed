#!/usr/bin/env python3
"""Safe GitHub Actions artifact downloads without bearer leakage on redirects."""
import io
import urllib.request
from urllib.parse import urlsplit


class SafeArtifactRedirect(urllib.request.HTTPRedirectHandler):
    """Strip GitHub API Authorization when the artifact URL changes origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        destination = urlsplit(newurl)
        if destination.scheme != "https":
            raise ValueError("artifact_redirect_requires_https")
        forwarded = super().redirect_request(req, fp, code, msg, headers, newurl)
        if forwarded is None:
            return None
        source = urlsplit(req.full_url)
        if (source.scheme, source.netloc) != (destination.scheme, destination.netloc):
            forwarded.remove_header("Authorization")
        return forwarded


def fetch_artifact_zip(url, github_token, max_bytes):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "api.github.com":
        raise ValueError("unexpected_artifact_api_origin")
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer " + github_token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "detector-r2-archive",
        },
    )
    opener = urllib.request.build_opener(SafeArtifactRedirect())
    with opener.open(request, timeout=120) as response:
        buffer = io.BytesIO()
        while True:
            block = response.read(min(1048576, max_bytes - buffer.tell() + 1))
            if not block:
                break
            if buffer.tell() + len(block) > max_bytes:
                raise ValueError("artifact_exceeded_size_limit")
            buffer.write(block)
    return buffer.getvalue()
