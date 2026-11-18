from __future__ import annotations

import pathlib
import tempfile
import unittest

from ajar.redact import (
    detect_secret_classes,
    scan_file_secret_classes,
    scrub_bytes,
    scrub_text,
    scrubbed_subprocess_env,
)


class TestRedact(unittest.TestCase):
    def test_scrubs_common_credential_classes(self) -> None:
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        gh_pat = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
        aws_key = "AKIA" + "IOSFODNN7EXAMPLE"
        pem = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEpAIBAAKCAQEA75+3testkeymaterial0123456789abcdef\n"
            "-----END RSA PRIVATE KEY-----"
        )
        signed_url = "https://bucket.s3.amazonaws.com/secret.tar?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Signature=deadbeefcafebabe0123456789"
        auth_hdr = "Authorization: Bearer super-secret-session-token-998877"

        sample = "\n".join([jwt, gh_pat, aws_key, pem, signed_url, auth_hdr])
        classes = detect_secret_classes(sample.encode("utf-8"))
        self.assertIn("jwt", classes)
        self.assertIn("provider_token", classes)
        self.assertIn("private_key", classes)
        self.assertIn("signed_url", classes)
        self.assertIn("authorization_header", classes)

        cleaned = scrub_text(sample)
        self.assertNotIn("eyJhbGciOi", cleaned)
        self.assertNotIn(gh_pat, cleaned)
        self.assertNotIn(aws_key, cleaned)
        self.assertNotIn("MIIEpAIBAAKCAQEA", cleaned)
        self.assertNotIn("deadbeefcafebabe0123456789", cleaned)
        self.assertNotIn("super-secret-session-token-998877", cleaned)
        self.assertIn("<REDACTED>", cleaned)
        self.assertEqual(detect_secret_classes(cleaned.encode("utf-8")), [])

    def test_scan_file_secret_classes_handles_chunk_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fp = pathlib.Path(td) / "chunked.bin"
            # Place a multi-line PEM private key right across the 1 MiB chunk boundary!
            pad = b"A" * (1024 * 1024 - 24)
            pem = (
                b"-----BEGIN OPENSSH PRIVATE KEY-----\n"
                b"b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQ==\n"
                b"-----END OPENSSH PRIVATE KEY-----\n"
            )
            fp.write_bytes(pad + pem + b"tail")
            found = scan_file_secret_classes(fp)
            self.assertIn("private_key", found)

    def test_scrub_bytes_binary_safe_and_extra_literals(self) -> None:
        raw = b"\x00\xff\xfeBearer secret-live-token-value-1234567890\x00custom-dyn-canary-99\x01"
        cleaned = scrub_bytes(raw, extra_literals=("custom-dyn-canary-99",))
        self.assertNotIn(b"secret-live-token-value-1234567890", cleaned)
        self.assertNotIn(b"custom-dyn-canary-99", cleaned)

    def test_scrubbed_subprocess_env_strips_ambient_credentials(self) -> None:
        base = {
            "PATH": "/usr/bin:/bin",
            "HOME": "/tmp/home",
            "OPENAI_API_KEY": "sk-proj-1234567890abcdefghijklmnop",
            "ANTHROPIC_API_KEY": "sk-ant-1234567890abcdefghijklmnop",
            "GITHUB_TOKEN": "ghp_1234567890abcdefghijklmnopqrstuvwx",
            "AWS_SECRET_ACCESS_KEY": "very-secret-aws",
            "LANG": "C.UTF-8",
        }
        env = scrubbed_subprocess_env(base_env=base, overrides={"CUSTOM_VAR": "ok"})
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", env)
        self.assertEqual(env["LANG"], "C.UTF-8")
        self.assertEqual(env["CUSTOM_VAR"], "ok")


if __name__ == "__main__":
    unittest.main()
