"""Trusted archive-only entry: accepts packages, never candidate Python or workflows."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.delivery.github import APIError, GitHub  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default="Jacelber/mtgo-data-releases")
    parser.add_argument("--target", default="Jacelber/mtgo-data")
    parser.add_argument("--token-env", help="Explicit narrow credential in Actions; omitted only in trusted local gh context")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Initialize empty archive control state, never reset existing state")
    upload = sub.add_parser("upload")
    upload.add_argument("candidate", type=Path)
    fetch = sub.add_parser("download")
    fetch.add_argument("identifier")
    fetch.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        if args.target not in {"Jacelber/mtgo-data", "Jacelber/mtgo-data-governance-verification"}:
            raise ValueError("Unsupported archive target")
        state_path = "state/pages.json" if args.target == "Jacelber/mtgo-data" else "state/verification-pages.json"
        client = GitHub(args.repository, token_env=args.token_env, state_path=state_path)
        client.private()
        if args.command == "init":
            state, sha = client.load_state()
            result = {"state": "already_initialized"} if sha else {"state": "initialized", "sha": client.save_state(state, sha)}
        elif args.command == "upload":
            result = client.archive(args.candidate, target=args.target)
        else:
            result = client.retrieve(args.identifier, args.destination, target=args.target)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (APIError, OSError, ValueError) as error:
        print(json.dumps({"state": "execution_failed", "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
