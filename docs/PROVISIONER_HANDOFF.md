# Factory-to-Provisioner request candidate

The existing Factory has a staged product under `products/<slug>`. This adapter emits a **dry-run-only** JSON candidate for the separately developed repository Provisioner.

Example:

```bash
python handoff_request.py --slug example-product --request-id req-1 \
  --owner shihuiarenjinba-png --repo-name example-app \
  --template shihuiarenjinba-png/approved-template \
  --source-sha <ACTUAL_40_CHARACTER_GITHUB_COMMIT> \
  --review-reference reviewed-pr-123 --out provisioner-request.json
```

This adapter **never calls GitHub APIs or creates repositories**. A caller must supply the *actual* full source commit SHA and an existing human review reference. It cannot attest that a claimed review truly occurred, that tests passed, or that the template exists. `dry_run=true` and `visibility=private` are always enforced.

**HOLD:** Until local Repository-Provisioner contract/schema is delivered and reconciled, no live dispatch and no automated repository creation. The existing factory `products/` promotion workflow remains unchanged. Downstream Windows-all-auto adapter, product QA and commercial release approval are separate.
