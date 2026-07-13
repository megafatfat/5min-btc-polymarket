#!/usr/bin/env python3
"""Apply BTC 5m integration patches to the local execution repo."""

from __future__ import annotations

import argparse
from pathlib import Path

RUNNER_REL = Path("src/live/pm_live_trade_runner.py")


def patch_runner(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    changed = False

    if "from dotenv import load_dotenv" not in text:
        text = text.replace(
            "from dataclasses import dataclass\n",
            "from dataclasses import dataclass\nfrom pathlib import Path\n\nfrom dotenv import load_dotenv\n",
        )
        insert = '\nload_dotenv(Path(__file__).resolve().parents[2] / ".env")\n'
        text = text.replace("from py_clob_client.constants import POLYGON\n", f"from py_clob_client.constants import POLYGON{insert}")
        changed = True

    if "--force-side" not in text:
        text = text.replace(
            'ap.add_argument("--execute", action="store_true")\n',
            'ap.add_argument("--execute", action="store_true")\n'
            '    ap.add_argument("--force-side", choices=["UP", "DOWN"], default="", help="Override HL signal side for BTC 5m skill integration")\n',
        )
        text = text.replace(
            "    side, mom, hl_start, hl_now, hl_vol = hl_signal(cfg.symbol)\n",
            "    side, mom, hl_start, hl_now, hl_vol = hl_signal(cfg.symbol)\n"
            "    if args.force_side:\n"
            "        side = str(args.force_side).upper()\n",
        )
        text = text.replace(
            '            "top_ask_notional": top_ask_notional,\n        }\n',
            '            "top_ask_notional": top_ask_notional,\n        }\n'
            "        if best_ask is not None:\n"
            "            entry_price = float(best_ask)\n",
        )
        text = text.replace(
            '"signal": {"side": side, "hl_momentum": mom, "hl_start_mid": hl_start, "hl_now_mid": hl_now, "hl_volatility": hl_vol},',
            '"signal": {"side": side, "forced_side": bool(args.force_side), "hl_momentum": mom, "hl_start_mid": hl_start, "hl_now_mid": hl_now, "hl_volatility": hl_vol},',
        )
        changed = True

    if "import urllib.request" in text:
        text = text.replace(
            "import time\nimport urllib.parse\nimport urllib.request\nfrom urllib.error import URLError\nfrom py_clob_client.client import ClobClient",
            "import time\n\nimport requests\nfrom py_clob_client.client import ClobClient",
        )
        old_get = '''def _get_json(url: str, params: dict | None = None, timeout: int = 25, retries: int = 3):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    last_err = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last_err = e
            if i < retries - 1:
                time.sleep(1.2 * (i + 1))
    raise RuntimeError(f"GET failed: {url} :: {last_err}")'''
        new_get = '''def _get_json(url: str, params: dict | None = None, timeout: int = 25, retries: int = 3):
    last_err = None
    headers = {"User-Agent": "Mozilla/5.0"}
    for i in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=timeout, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            last_err = e
            if i < retries - 1:
                time.sleep(1.2 * (i + 1))
    raise RuntimeError(f"GET failed: {url} :: {last_err}")'''
        text = text.replace(old_get, new_get)

        old_post = '''def _post_json(url: str, payload: dict, timeout: int = 25, retries: int = 3):
    body = json.dumps(payload).encode("utf-8")
    last_err = None
    for i in range(retries):
        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last_err = e
            if i < retries - 1:
                time.sleep(1.2 * (i + 1))
    raise RuntimeError(f"POST failed: {url} :: {last_err}")'''
        new_post = '''def _post_json(url: str, payload: dict, timeout: int = 25, retries: int = 3):
    last_err = None
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    for i in range(retries):
        try:
            resp = requests.post(url, json=payload, timeout=timeout, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            last_err = e
            if i < retries - 1:
                time.sleep(1.2 * (i + 1))
    raise RuntimeError(f"POST failed: {url} :: {last_err}")'''
        text = text.replace(old_post, new_post)
        changed = True

    if changed:
        path.write_text(text, encoding="utf-8")
        print(f"Patched: {path}")
    else:
        print(f"Already patched: {path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--repo",
        default=str(Path(__file__).resolve().parents[2] / "pm-hl-conservative-plus-repo"),
    )
    args = ap.parse_args()
    runner = Path(args.repo) / RUNNER_REL
    if not runner.exists():
        raise SystemExit(f"Runner not found: {runner}")
    patch_runner(runner)


if __name__ == "__main__":
    main()