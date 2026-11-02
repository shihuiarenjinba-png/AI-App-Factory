# Buyer validation protocol — image delivery change evidence

Status: **NOT RUN / NO BUYER RESPONSES**. This protocol is not evidence of demand, product-market fit, or a price commitment. Preserve `market_fit=MARKET_FIT_HOLD`, score **64/100**, and `why_pay_verified=false` until independent evidence is reviewed.

## Participants and independence

Recruit **five** real people who currently deliver, receive, archive, or audit image folders (small creative studios, freelance photographers/designers, production coordinators, digital asset custodians). Record their role, approximate monthly image-delivery volume, current tool, and whether they already pay for change tracking. Do not substitute teammates, synthetic respondents, or generated answers for independent buyers. Obtain consent; never upload real client images or identifying records to the repository.

## Standard task, same for every participant

Use two synthetic folders of valid images: 1 unchanged, 1 removed, 1 added, and 1 same-name image with different content. Give the participant only the business task: "You received a revised delivery folder. Produce an understandable change record for the client without altering any original files."

1. Without coaching, have the participant try the free/current tool they already use; note whether it can create a comparable customer-readable change record (not merely duplicate detection).
2. With Offline Image Inventory Desk at 1024x768, have them record the baseline, compare the revised folder, export CSV, JSON, and human-readable TXT, and switch EN/JA.
3. Close and reopen the app; reopen the saved baseline, compare again, and verify deterministic counts.
4. Introduce a simulated read-denied image; ask whether the user notices the explicit failure and refrains from delivering a stale report.
5. Have them identify exactly what SHA-256 establishes and what report creation time **cannot** prove. Inspect source-image hashes before/after.

Record timestamps, click count, assistance, errors, output correctness, source preservation, confusion points, and whether a client would accept the TXT report. Distinguish actual Windows EXE launch from scripted source-GUI interaction; hosted runner evidence is `CLOUD_WINDOWS_GUI_SMOKE`, **not** `LOCAL_GUI_PASS`.

## Free alternatives to compare fairly

- **FreeFileSync**: free folder comparison/synchronization; verify whether the participant's actual workflow already produces an acceptable delivery change summary.
- **WinMerge**: free file/folder comparison; assess report readability and setup time.
- **digiKam**: free image catalog and duplicate management; do not falsely claim duplicate detection alone is a paid differentiator.

Check each alternative's current capabilities and licensing on the test date; do not predeclare a winner. No proprietary code, UI layout, or branding copying.

## Response sheet (one row per actual participant; leave blank until tested)

| participant_id | role | existing_tool | monthly_deliveries | task_success_free | task_success_product | time_free_sec | time_product_sec | assisted_steps | critical_errors | client_accepts_txt | source_unchanged | willingness_to_pay_JPY | reason_to_pay | reason_not_to_pay | interview_date | consent |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | | | | | | | | |

Ask independently: "Would you buy this for your own work today, at ¥500, ¥1,000, ¥2,000 one-time, or not at all?" Ask for an actual purchase/paid pilot decision where feasible, not only hypothetical interest. Record the exact quoted answer and context, not a paraphrased "yes."

## Review gate

Re-score all seven weighted rubric dimensions only after verifying five authentic records and independent review SHA. `why_pay_verified=true` requires credible, specific evidence that at least some target buyers choose this over free alternatives and are prepared to pay. No automatic threshold or fabricated demand. **80+ alone is not sufficient**: all GO conditions, independent review, Windows GUI QA, and owner-controlled promotion remain required. Do not start Identity/CAS/MSIX/Store work from this document.


## Runnable evidence kit (2026-11-02)
The Windows image-snapshot workflow now packages the **actual unsigned EXE** with
synthetic `baseline/` and `delivery/` folders (one each: unchanged, modified,
removed, added), SHA-256 manifest, empty `participant-responses.csv`, and
hosted packaged-EXE E2E screenshots/logs. Download the
`image-snapshot-SYNTHETIC-BUYER-TEST-KIT-NO-REAL-RESPONSES` artifact from the
exact-head workflow run. It is a **test kit, not five completed interviews**.

For each consenting independent participant, use their own Windows environment
at 1024x768 and the bundled EXE. The `buyer_validation_evidence.py` CLI
supports `event --out <kit> --participant P01 --phase product --action start`
and `event --out <kit> --participant P01 --phase product --action stop --clicks N --errors N`
to time real sessions. Supported phases: `free`, `product`, `restart`,
`read_error`. Manually fill the response CSV with **only authentic** answers.
Run `verify --out <kit>` after each test to detect any fixture image or EXE
SHA changes. Keep human response sheets and any real client data **off GitHub**.
No CI step fills responses or promotes the market score.

## Uncoached 30-second → compare → delivery → recipient journey (2026-11-02)

This is a **manual observation contract**, not a claim that a buyer has been tested. The exact-head synthetic kit binds the same EXE SHA-256, source SHA and four image-state hashes for all five participants. Give each person an untouched private copy; run `verify --out <kit>` before and after. Never replace the packaged EXE with a rebuilt binary. Run on real Windows, not a cloud CI screenshot.

Observer only: compare the participant’s **existing/free tool first** (WinMerge or FreeFileSync where relevant), then launch the packaged product without explaining the controls. Start the `first_30sec` event and stop at approximately 30 seconds; write down whether they can state the goal and the first action without prompting. Next use the product to record the BEFORE folder, compare the AFTER folder and save the **HTML client report with previews**; log the `product` and `delivery` phases separately. Hand the saved HTML to a recipient **without a walkthrough**. Ask them to explain which images were added, removed, modified and unchanged, and what SHA-256 and report creation time do *not* prove. Log `recipient_review` and verbatim confusion privately. Then restart/reopen and test the separate invalid-image folder; log `restart` and `read_error` and confirm no stale success is offered. Do not coach, grade, or fill answers during CI.

Use `event --out <kit> --participant P01 --phase <phase> --action start` followed by `... --action stop --clicks N --errors N` for each phase **in order**: `free`, `first_30sec`, `product`, `delivery`, `recipient_review`, `restart`, `read_error`. In `participant-responses.csv`, fill the appended columns `first_30sec_goal_understood`, `recipient_can_identify_changes`, `recipient_can_explain_limits` with observed `yes` or `no` (negative observations are valid), and `recipient_feedback` with the recipient’s actual explanation or confusion. Existing willingness-to-pay and consent fields remain mandatory for a complete *manual* journey. The audit checks completeness/order but **cannot authenticate a person or infer purchase intent**. Run `python buyer_validation_audit.py --out <kit>` privately; status always remains `HUMAN_REVIEW_REQUIRED`, score 64, `why_pay_verified=false` until independent review. Never upload filled CSV/events or identifying records to GitHub.

Fair comparison verified 2026-11-02: [WinMerge official project](https://github.com/WinMerge/winmerge) already offers free folder comparison; [FreeFileSync official manual](https://freefilesync.org/manual.php) documents free folder comparison. Record what each person actually achieves rather than declaring either tool inferior. This protocol does not authorize promotion, Identity rebind, MSIX or Store submission.
