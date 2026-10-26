# AI-App-Factory

## Purpose
Independent app development factory. Uses GitHub Actions and OpenAI Codex to
research public GitHub issue demand signals, create a prototype, run two bounded
improvement rounds, and repeat. GitHub issues are weak market proxies, NOT sales proof.

This is a review-gated prototype infrastructure, not a finished autonomous Store publisher.

## Activation (manual, once per repository)
1. Review tests and merge the bootstrap Draft PR into main (scheduler requires default branch).
2. Under Settings -> Secrets and variables -> Actions, create secret OPENAI_API_KEY.
3. Under Actions -> Variables, create FACTORY_ENABLED with value true.
4. Under Settings -> Actions -> General, enable GitHub Actions creation of pull requests.
5. Set a provider-side API usage budget; check Actions job and billing quotas.
6. Manually dispatch "Factory 15 minute cycle" once and inspect all job logs.
7. Review the resulting Draft PR; merge only when acceptable.

The Actions CRON runs every 15 minutes, but it may be delayed or dropped.
The workflow pauses if an unmerged codex/factory-* PR exists, preventing overlap.
The state in factory/state.json advances only when that human-reviewed PR merges.
Schedule on the feature branch alone is INACTIVE.

Stages: research -> build -> improve #1 -> improve #2 -> research next product.
Products are staged in products/<slug>; proposals are in proposals/<slug>.json.
No new GitHub repos are created automatically in this first phase.

## Local smoke verification

    python -m unittest discover -s tests -v
    python -m py_compile factory.py

- Codex runs with workspace permissions and no GitHub write token.
- A clean CI runner validates generated candidate files, type, provenance, paths,
  symlinks, size and test execution (timeouts).
- A separate write-capable runner only creates a Draft PR; never main commits or merges.
- The OpenAI key and GitHub write token are not passed to generated products.
- No actual Windows UI test, commercial licensing verification, installer signing,
  MSIX, Partner Center upload or Microsoft certification is performed by this repo.
- Windows-data, Windows-checker, Windows-Automator and Windows-all-auto remain
  downstream independent systems, currently with unfinished live integration.
- Windows QA, identity and final commercial gate are mandatory before any sale.
- All work uses reviewed branches; do not bypass a HOLD.

## Failure circuit breaker and test isolation

After 3 failed scheduled workflow runs within 24 hours the factory refuses further
AI invocations until the window clears and the operator reviews errors.
Generated tests execute in a memory/CPU/PID-bounded, network-disabled, non-root,
read-only Docker container. The clean promotion job never executes generated tests.
