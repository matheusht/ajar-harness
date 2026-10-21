#!/usr/bin/env python3
"""Synthetic local note workflow for review setup; no network or real user data."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('draft', 'publish'))
    parser.add_argument('--actor', required=True)
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--note', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    args = parser.parse_args()
    try:
        policy = json.loads(args.policy.read_text())
        note = json.loads(args.note.read_text())
        owner = args.actor == note['owner']
        if args.action == 'draft':
            allowed = owner
            destination = args.state / 'draft.txt'
        else:
            allowed = ((owner and policy['allow_owner_publish'] is True)
                       or (args.actor == note['delegate']
                           and policy['allow_delegate_publish'] is True))
            destination = args.state / 'published.txt'
        if not allowed:
            print(json.dumps({'effect': 'denied', 'actor': args.actor,
                              'action': args.action, 'policy': policy['version']}))
            return 3
        text = note['text'] if args.action == 'draft' else (args.state / 'draft.txt').read_text()
        destination.write_text(text)
        print(json.dumps({'effect': 'written', 'file': destination.name,
                          'actor': args.actor, 'policy': policy['version']}))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'effect': 'unavailable', 'error': type(error).__name__}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
