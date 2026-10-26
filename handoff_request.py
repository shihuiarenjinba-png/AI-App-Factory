"""Generate a review-only, dry-run Provisioner request from an existing product."""
import argparse
import json
import re
from pathlib import Path

SLUG = re.compile(r"^[a-z][a-z0-9-]{3,39}$")
IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
REPO = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9_.-]+$")
SHA = re.compile(r"^[0-9a-fA-F]{40}$")
LANES = {"app": ("APP", "AI-App-Factory"),
         "game": ("GAME", "AI-Game-Factory")}


def request(root, slug, request_id, repository_owner, repository_name,
            template_repository, source_sha, review_reference):
    if not SLUG.fullmatch(slug):
        raise ValueError("invalid product slug")
    if not IDENT.fullmatch(request_id):
        raise ValueError("invalid request id")
    if not IDENT.fullmatch(review_reference):
        raise ValueError("missing review reference")
    if not REPO.fullmatch(f"{repository_owner}/{repository_name}"):
        raise ValueError("invalid destination repository")
    if not REPO.fullmatch(template_repository):
        raise ValueError("invalid template repository")
    if not SHA.fullmatch(source_sha):
        raise ValueError("full 40-character source SHA required")
    config = json.loads((root / "factory/config.json").read_text(encoding="utf-8"))
    kind = config.get("kind")
    if kind not in LANES:
        raise ValueError("unsupported factory kind")
    product_dir = root / "products" / slug
    if product_dir.is_symlink() or not product_dir.is_dir():
        raise ValueError("product directory missing or symlink")
    manifest_path = product_dir / "manifest.json"
    if manifest_path.is_symlink():
        raise ValueError("manifest symlink not permitted")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("slug") != slug or manifest.get("kind") != kind:
        raise ValueError("product manifest does not match factory kind/slug")
    if manifest.get("entry") != "main.py":
        raise ValueError("unrecognized product entry")
    typ, factory = LANES[kind]
    return {
        "schema_version": "1.0",
        "request_id": request_id,
        "product_type": typ,
        "source_factory": factory,
        "repository_owner": repository_owner,
        "repository_name": repository_name,
        "template_repository": template_repository,
        "visibility": "private",
        "dry_run": True,
        "product_slug": slug,
        "product_source_sha": source_sha,
        "review_reference": review_reference,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    p.add_argument("--slug", required=True)
    p.add_argument("--request-id", required=True)
    p.add_argument("--owner", required=True)
    p.add_argument("--repo-name", required=True)
    p.add_argument("--template", required=True)
    p.add_argument("--source-sha", required=True)
    p.add_argument("--review-reference", required=True)
    p.add_argument("--out", type=Path)
    args = p.parse_args(argv)
    try:
        payload = request(args.root, args.slug, args.request_id,
                          args.owner, args.repo_name, args.template,
                          args.source_sha, args.review_reference)
        encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(encoded, encoding="utf-8")
        print(encoded, end="")
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"HOLD: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
