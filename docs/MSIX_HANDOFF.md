# Factory → Windows-all-auto: MSIX引継ぎ

Factoryは販売担当ではなく「製品のコード・Windows/MSIX候補の作成担当」です。

## 自動受け渡し
- products/<slug>/... に変更が入ると .github/workflows/msix-export.yml がWindows Runnerで検査する。
- store/approved-identity.json と StoreLogo.png、Square150.png、Square44.png の実物がある場合だけ tools/build_windows_msix.py でPyInstaller→MakeAppx MSIX候補生成。
- tools/msix_handoff.py が実MSIX内部のName/Publisher/Versionと承認済み入力を比較し、package.msixとhandoff.jsonをまとめる。
- GitHub Actions Artifact factory-msix-handoff-<slug> を5日間保存。MSIXをgit repositoryにコミットしない。
- Windows-all-autoは15分周期にファクトリーArtifactを自動取得し、SHAとsource commitを再照合したうえでローカルPC用QA Artifactを作る。
- ローカル受信スクリプトはOllama不要、既存SHAを再ダウンロードせず、20件/2GiBで停止する。

## 明示的なHOLD
- 新製品に承認済みMicrosoft Store Identityがない場合、MSIXは作れない（勝手に作成しない）。
- 正しい新製品の流れは「Factoryがソースを作る → Windows-all-autoで初期登録・Identity予約 → 公式情報をFactoryへ戻す → MSIX生成 → 中央へ受け渡し」であり、このIdentity返信は未実装。
- 製品のソース生成・15分ごとのAI自動改修はまだ実運転できていない。FactoryのDraft PRもmain未マージ。
- MSIXはQA_UNSIGNED候補であり、インストール/起動、複数UIのスクリーンショット、署名、WACK、Partner Center申請は未実施。
- Factory CIのPASSは配布までの全工程の合格ではない。

## 参照
中央担当: https://github.com/shihuiarenjinba-png/Windows-all-auto/tree/codex/windows-all-auto-integration-20261026
中央仕様: docs/FACTORY_TO_STORE_HANDOFF.md
