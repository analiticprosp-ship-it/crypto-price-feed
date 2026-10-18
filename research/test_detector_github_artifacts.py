#!/usr/bin/env python3
"""Offline checks for GitHub API to signed Actions artifact redirects."""
import unittest
import urllib.request
from research.detector_github_artifacts import SafeArtifactRedirect, fetch_artifact_zip


class RedirectTests(unittest.TestCase):
    def setUp(self):
        self.handler = SafeArtifactRedirect()
        self.request = urllib.request.Request(
            "https://api.github.com/repos/example/repo/actions/artifacts/123/zip",
            headers={"Authorization": "Bearer secret", "User-Agent": "detector-test"},
        )

    def test_external_signed_url_does_not_receive_bearer(self):
        redirect = self.handler.redirect_request(
            self.request, None, 302, "Found", {},
            "https://results-receiver.actions.githubusercontent.com/object?signed=1",
        )
        self.assertNotIn("Authorization", redirect.headers)
        self.assertNotIn("Authorization", redirect.unredirected_hdrs)
        self.assertEqual(redirect.get_header("User-agent"), "detector-test")

    def test_same_origin_keeps_bearer(self):
        redirect = self.handler.redirect_request(
            self.request, None, 302, "Found", {},
            "https://api.github.com/another/path",
        )
        self.assertEqual(redirect.get_header("Authorization"), "Bearer secret")

    def test_http_redirect_rejected(self):
        with self.assertRaises(ValueError):
            self.handler.redirect_request(
                self.request, None, 302, "Found", {}, "http://other.example/data",
            )

    def test_untrusted_origin_rejected(self):
        with self.assertRaises(ValueError):
            fetch_artifact_zip("https://other.example/data", "secret", 1024)


if __name__ == "__main__":
    unittest.main()
