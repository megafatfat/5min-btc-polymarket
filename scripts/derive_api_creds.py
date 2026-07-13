#!/usr/bin/env python3
"""Derive Polymarket CLOB API credentials from wallet private key."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def main() -> int:
    key = os.getenv("PM_PRIVATE_KEY", "").strip()
    funder = os.getenv("PM_FUNDER") or os.getenv("PM_ADDRESS") or None
    sig = int(os.getenv("PM_SIGNATURE_TYPE", "2"))

    if not key or key.startswith("your_"):
        print("Fill PM_PRIVATE_KEY in ~/Projects/pbt-5m-enhanced/.env first.", file=sys.stderr)
        return 1

    client = ClobClient(
        host=os.getenv("PM_CLOB_BASE", "https://clob.polymarket.com"),
        chain_id=POLYGON,
        key=key,
        signature_type=sig,
        funder=funder,
    )
    creds = client.create_or_derive_api_creds()

    print("Derived API credentials (save to .env if you want):")
    print(f"PM_API_KEY={creds.api_key}")
    print(f"PM_API_SECRET={creds.api_secret}")
    print(f"PM_API_PASSPHRASE={creds.api_passphrase}")
    print()
    print("Note: with PM_PRIVATE_KEY set, the runner can derive these automatically.")
    print("You only need PM_PRIVATE_KEY + PM_FUNDER for live trading.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())