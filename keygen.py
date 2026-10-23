#!/usr/bin/env python3
"""B5 key generator — create the Ed25519 keypairs for the trust bridge.

Two keypairs run the premium ecosystem:

  1. SYNC KEYPAIR
       private  -> GitHub secret  LUMA_SYNC_PRIVATE_KEY   (ember-signal repo,
                   used by the data-sync workflow to sign POST /api/sync/run)
       public   -> Render env var LUMA_TRUST_PUBLIC_KEYS  (ember-signal-web,
                   JSON map {"sync-main": "<base64>"})

  2. PURGE KEYPAIR (optional, for the B1 worker cache purge)
       private  -> Render env var SYNC_PURGE_KEY           (ember-signal-web,
                   sync_service signs its purge call with it)
       public   -> Worker secret  ADMIN_PUBLIC_KEY          (luma-bridge worker,
                   authorises POST /api/signals/purge)

  3. RESPONSE-SIGNING KEYPAIR (optional, enables B1 upstream verification)
       private  -> Render env var LUMA_RESPONSE_SIGNING_KEY (ember-signal-web)
       public   -> Worker secret  UPSTREAM_PUBLIC_KEY        (luma-bridge)

Usage:
    python keygen.py                 # generate all three, print setup snippet
    python keygen.py --role sync     # just the sync keypair

The private keys are printed ONCE to stdout — save them where they belong,
then treat the terminal output as sensitive and clear it.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def generate() -> tuple[str, str]:
    private_key = Ed25519PrivateKey.generate()
    seed = private_key.private_bytes_raw()  # 32-byte seed == "raw private key"
    public = private_key.public_key().public_bytes_raw()
    return base64.b64encode(seed).decode("ascii"), base64.b64encode(public).decode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Ed25519 trust-bridge keypairs")
    parser.add_argument("--role", choices=["sync", "purge", "response", "all"], default="all")
    args = parser.parse_args()

    roles = ["sync", "purge", "response"] if args.role == "all" else [args.role]
    generated: dict[str, tuple[str, str]] = {}

    for role in roles:
        generated[role] = generate()

    print("=" * 72)
    print("LUMA FOUNDRY — B5 TRUST BRIDGE KEYS (Ed25519)")
    print("=" * 72)

    if "sync" in generated:
        priv, pub = generated["sync"]
        print("\n[1] SYNC KEYPAIR — authorises the B4 data-sync workflow")
        print(f"    GitHub secret  LUMA_SYNC_PRIVATE_KEY = {priv}")
        print(f'    Render env     LUMA_TRUST_PUBLIC_KEYS = {json.dumps({"sync-main": pub})}')

    if "purge" in generated:
        priv, pub = generated["purge"]
        print("\n[2] PURGE KEYPAIR — lets the sync service clear the B1 edge cache")
        print(f"    Render env     SYNC_PURGE_KEY = {priv}")
        print(f"    Worker secret  ADMIN_PUBLIC_KEY = {pub}")

    if "response" in generated:
        priv, pub = generated["response"]
        print("\n[3] RESPONSE-SIGNING KEYPAIR — lets the B1 worker verify /api/signals")
        print(f"    Render env     LUMA_RESPONSE_SIGNING_KEY = {priv}")
        print(f"    Worker secret  UPSTREAM_PUBLIC_KEY = {pub}")

    print("\nNEXT STEPS")
    print("  1. Store the private halves as secrets/env vars above (never in git).")
    print("  2. Rotation later: generate a new pair, ADD the new key-id to")
    print("     LUMA_TRUST_PUBLIC_KEYS alongside the old one, switch the caller,")
    print("     then remove the old entry — zero downtime.")
    print("  3. Clear this terminal output — the private seeds were printed here.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
