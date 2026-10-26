# APP Factory → local package Provisioner (contract adapter)

This branch adds `package_handoff_request.py`, a **read-only** adapter for the
current `Repository-Provisioner-app/package_job.py` schema (version `"1.0"`).
It is distinct from the older repository-creation adapter on the stacked
`codex/provisioner-handoff-20261026` branch. Do not dispatch that old JSON to
the local package worker.

## Produce a candidate

From a **clean** checkout of
`codex/factory-autoloop-20261026` with an actual committed APP product:

```bash
python package_handoff_request.py --slug example-product --request-id app-20261026-001 > app-package-job.json
```

The CLI refuses another branch, modified or untracked product files, a
missing/uncommitted manifest, missing executable or smoke test, wrong product
kind, and an absent/invalid proposal title. It reads the exact local Git HEAD
as `source_sha`; the caller cannot choose a different SHA. It never sends
network requests, invokes a build, reserves a name, or writes to GitHub.

**Integration note:** This adapter is developed on
`codex/app-package-handoff-20261026`, branched from the autoloop branch.
To execute it for a real product, the adapter must first be integrated into
the intended Factory work branch via an explicitly reviewed change. Running
the producer from this development branch intentionally returns HOLD.

The JSON keys and action names match the existing APP intake CLI. The local
operator can then run, after transferring the reviewed JSON:

```bash
python package_job.py --input app-package-job.json --output receipt.json
```

That command currently returns only `DRY_RUN`. It does **not** verify the
remote GitHub branch HEAD, build MSIX, query Partner Center, return official
Identity, or trigger Windows-all-auto. Those are separate unimplemented
stages. A real local worker must authenticate and verify that the remote
branch HEAD equals `source_sha` before a pinned checkout and must recheck
HEAD before any official Identity return.

## Safety gates

- Only APP from `shihuiarenjinba-png/AI-App-Factory`.
- No OpenAI API key, paid Codex API, or Ollama is needed for this adapter.
- Store ID is issued by Partner Center, not inferred from MSIX/PFN/SID.
- Return target is `products/<slug>/store/approved-identity.json` on an
  approved `codex/*` Factory branch, using Windows-all-auto's separate
  identity routing and atomic HEAD check.
- No main/release writes, unapproved merges, Store submission, or fabricated
  Identity/price/security data.

## Verification

`python -m unittest discover -s tests -v` runs both existing Factory tests
and this adapter's offline Git tests. CI PASS means contract producer tests
only, not real package manufacture or end-to-end Artifact transport.
