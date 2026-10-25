全部パスしました（`TZ=UTC npm test`、CI と同じ条件）。

- **最後の全体 jest 実行**: 93 テストスイート中 93 パス、794 テスト中 794 パス（約 3.4 秒）
- **それより前の TZ 別実行**: `npm test` は `&&` でつないだ実行の連なりです。Pacific/Auckland、Europe/London、America/Whitehorse、ホストの TZ でのコアテスト、続いて Europe/Paris、London、New_York、Auckland での timezone プラグインテストが走ります。どれか 1 つでも失敗すると最後の実行まで進まないので、全段階がパスしています。
- **カバレッジ**: 100% 行カバレッジの閾値を満たしています。分岐カバレッジは 100% 未満のファイルがいくつかあります（`preParsePostFormat` 93.75%、`timezone` 97.22%、`utc` 96.08%）。ただし閾値は行カバレッジだけなので、失敗にはなりません。

出力に Handlebars の "Access has been denied..." という警告が何度か出ますが、これはカバレッジレポートを生成するツールが出しているもので、テスト結果には影響しません。
