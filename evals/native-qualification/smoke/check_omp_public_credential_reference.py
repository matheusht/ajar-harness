#!/usr/bin/env python3
"""Fail-first checks for the public OpenAI credential environment reference.

Run: python3 evals/native-qualification/smoke/check_omp_public_credential_reference.py
No provider, Docker daemon, or real credential is used.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))

from engagement_contract import ContractError, safe_publication  # noqa: E402


def require_rejected(data: bytes, *, known_secrets: tuple[bytes, ...] = ()) -> None:
    try:
        safe_publication(data, known_secrets=known_secrets)
    except ContractError as error:
        assert error.code == 'publication_secret', error.code
    else:
        raise AssertionError(f'unsafe publication accepted: {data!r}')


def main() -> int:
    accepted = (
        b'{"apiKey":"OPENAI_API_KEY"}',
        b'{ "other": { "apiKey" : "OPENAI_API_KEY" } }',
        b'{"other":[{"apiKey"\t:\t"OPENAI_API_KEY"}]}',
        '{"apiKey": "OPENAI_API_KEY"}'.encode('utf-16'),
    )
    for data in accepted:
        assert safe_publication(data) == data

    rejected = (
        b'{"apiKey":"sk-live-example-secret"}',
        b'{"apikey":"OPENAI_API_KEY"}',
        b'{"api_key":"OPENAI_API_KEY"}',
        b'{"apiKey":"openai_api_key"}',
        b'apiKey=OPENAI_API_KEY',
        json.dumps({'note': '"apiKey":"OPENAI_API_KEY"'}).encode(),
        b'{"apiKey":"other","token":"OPENAI_API_KEY"}',
    )
    for data in rejected:
        require_rejected(data)

    # A name that is a valid public reference still becomes sensitive when the
    # caller supplies that exact value as a known secret.
    require_rejected(b'{"apiKey":"OPENAI_API_KEY"}',
                     known_secrets=(b'OPENAI_API_KEY',))
    print(json.dumps({'accepted': len(accepted), 'rejected': len(rejected) + 1,
                      'provider_or_docker_contact': False}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
