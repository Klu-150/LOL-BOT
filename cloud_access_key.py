"""Run privately to create one user's cloud access key; never commit its output."""
import argparse
import hashlib
import json
import re
import secrets

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('username')
    parser.add_argument('--role', choices=['viewer', 'trader'], default='viewer')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', args.username):
        parser.error('Use 1–40 letters, numbers, underscores or hyphens')
    key = secrets.token_urlsafe(32)
    print('Private access key (enter only in the app):', key)
    print('User configuration (merge user entries into LEAGUE_USERS_JSON):')
    print(json.dumps({args.username: {'sha256': hashlib.sha256(key.encode()).hexdigest(), 'role': args.role}}))
