# 月次締め：未処理証憑の計数範囲（2026-11-02 JST）

## 現行仕様と修正

月次仕訳・試算表・損益・貸借は対象月末を基準とする。一方、
`receipt_queue` は現在の `status` と登録時刻だけを保存し、過去の
ステータス遷移履歴を持たない。このため「対象月末時点の未処理証憑件数」
を遡及再現することは**できない**。

`unprocessed_receipts` は互換性維持のため現在キュー全期間の未処理数を返す。
`unprocessed_receipts_scope=CURRENT_QUEUE_ALL_DATES_NOT_HISTORICAL_AS_OF`
および `unprocessed_receipts_as_of_month_end=null` を追加し、HTMLに
「現在の未処理証憑」「対象月末時点の履歴件数ではありません」と表示する。
未来日付の証憑が混在する回帰fixtureを追加した。

将来、真の月末時点件数が必要なら、イベント時刻付きの状態遷移監査ログ
（登録・処理・再開）を設計し、時点再生可能性をテストしてから追加する。
現行データから推測して過去の数値を捏造しない。

## 2026-11-02 一次資料確認

- 国税庁「No.2070 青色申告制度」:
  https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2070.htm
  日々の取引の記帳と帳簿・証憑保存の必要性を確認。現行のキュー件数が
  過去の帳簿時点残高を意味するとは扱わない。
- 国税庁「電子帳簿保存」:
  https://www.nta.go.jp/about/introduction/torikumi/week/dennsityoubo.htm
  電子取引で受領したデータは紙の出力だけで代替しない方針を維持。

本修正は税務適合認定、控除判定、電子保存法適合の宣言ではない。
