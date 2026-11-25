# Focus Session Desk — source-bound DRY_RUN request

This artifact is for owner 36 to review. It is **not submitted** to Microsoft Partner Center and does not authorize any write.

- Request: \`app-focus-session-desk-fb6293839bc7\`
- Source: \`shihuiarenjinba-png/AI-App-Factory\`, branch \`codex/focus-store-assets-gate-20261118\`
- Exact source / expected HEAD: \`fb6293839bc7b0bbff0a6d1d3c04e2f8f5942e79\`
- Partner Center selection: **MSIX or PWA app** (\`MSIX_OR_PWA_APP\`)
- Scope: read-only revalidation of the existing product Identity against the current source.
- Historical approved Identity remains bound only to \`8b00bc4e90828c4282463826873aa8dfd2eb93f4\` / \`app-focus-session-desk-8b00bc4e9082\`; it is not reused.
- Official \`store_id\`, Identity \`name\`, \`publisher\`, \`version\`, evidence URL and operator attestation must be read from Partner Center by the authorized operator. No value is inferred here.
- Package Version remains \`HOLD\`; no MSIX is built.

Safety flags: \`dry_run=true\`, \`request_submitted=false\`, \`partner_center_write=false\`, \`identity_write=false\`, \`msix_build=false\`, \`store_submission=false\`, \`store_publication=false\`.

The workflow must refuse source-branch drift and any product-tree change from the pinned source SHA. Replaying the same idempotency key and request SHA is a no-op; a different payload under the same key is rejected.
