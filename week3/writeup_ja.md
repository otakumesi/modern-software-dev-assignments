# Week 3 Write-up（日本語版）

> 提出用の正本は英語版 [`writeup.md`](writeup.md) です。このファイルは同じ内容を日本語で書いたものです。

**Skill名**と対象リポジトリ:
> `dayjs-bug-triage`（[`week3/dayjs-bug-triage/`](dayjs-bug-triage/SKILL.md)）。対象は [iamkun/dayjs](https://github.com/iamkun/dayjs) の `dev` ブランチ、コミット `436bde0` です。
> Claude Code からは symlink（`.claude/skills/dayjs-bug-triage -> ../../week3/dayjs-bug-triage`）を通じて見つかります。


## Part I: ワークフロー

**ワークフローの内容**と、Skillにする価値:
> 報告された dayjs のバグ（issue 番号か URL）を受け取り、次の手順を踏んで判定を1つ出します。
> 1. 現在の `src` に対する最小の jest 再現テストを作る
> 2. 決まったタイムゾーン群で実行する
> 3. Moment と比べる
> 4. 既存の issue や PR を探す
> 5. 根拠つきで判定を出す（CONFIRMED / CONFIRMED-ENV / EXPECTED / USAGE / FIXED-ON-DEV / DUPLICATE-OR-HAS-PR / CANNOT-REPRODUCE のいずれか）
>
> dayjs のトラッカーには、質のばらつく報告が絶えず届きます。直近の open な「bug」issue を30件見ただけでも、次のようにさまざまでした。
> - 本物のバグ（#3246）
> - ロケールの慣習どおりで、仕様どおりのもの（#3142、sv-fi）
> - 特定のタイムゾーンでしか起きないもの（#3003）
> - 既に PR が出ているもの（#3048〜#3062）
>
> どれにも同じチェックリストが当てはまり、どの手順を飛ばしても誤った結論になります。だから Skill にする価値があります。

**判断が必要な場面**（実行するだけでなく、エージェントが判断しなければならないこと）:
> どの判定を下すか、です。特に難しいのは次の4つです。
> 1. **報告者の「期待値」は本当に期待されるものか。** 決め手は報告者の意見ではなく、Moment との互換性（ロケール文字列なら `Intl`）です。例外は、Moment 自体も客観的に誤っている場合です。
> 2. **「UTC で成功した」だけで CANNOT-REPRODUCE と言えるか。** 言えません。入力が過去のオフセット変更、DST、日付の境界の近くにないかを判断してからでないと、諦めてはいけません。
> 3. **再現できたら作業は終わりか。** 根本原因を直す PR が既にあれば、出すべきものは「PR #N をレビューしてください」であり、競合する修正ではありません。
> 4. **報告者の原因分析は正しいか。** コードを読んで確かめるべき手がかりであって、結論ではありません。

**手作業で実行してわかった、予想していなかったこと**:
> Skill を書く前に、scratch 上の dayjs clone で2件を手作業でトリアージしました。そのとき書いた再現テストは `evidence/manual-issue-3246.test.js` と `evidence/manual-issue-3003.test.js` にあります。
> - **#3246**（calendar の callback が `referenceTime` を無視する）: UTC・Tokyo・New York のすべてで再現し、Moment 2.29.2 は正しく動くので、本物のバグです。ところが `gh pr list` を見ると、**修正する PR #3248 が既にありました**。難しいのは再現だと思っていましたが、実際に難しかったのはどこで止めるかの判断でした。このトラッカーでは、再現できるバグの多くに既に PR があります。
> - **#3003**（`dayjs('1981-12-01').daysInMonth()` が 1 を返す）: **UTC と Tokyo では成功し**、失敗するのは `Asia/Kuala_Lumpur` と `Asia/Singapore` だけでした。1982-01-01 にオフセットが +07:30 から +08:00 に変わってその日の現地 0 時が存在しないため、`endOf('M')` が `1982-01-01T00:29:59+08:00` になります。自分のマシンのタイムゾーンだけで試していたら、誤って CANNOT-REPRODUCE と判定していたはずです。#3137 と PR #3175 も同じ根本原因です。
> - issue の再現コードはたいてい `require('dayjs')`（npm で公開されたビルド）を使います。それではなく `../../src` で試さないと、「まだ壊れている」のか「dev では修正済みで未リリース」なのかを区別できません。
> - issue やコメントには、AI の助けを借りた、もっともらしい「根本原因」の分析がよく付いています。確かめた2件ではどちらも正しかったのですが、Skill はそれを写すのではなく検証しなければなりません。


## Part II: Skill

**description**（原文のまま）:
```
Reproduce and triage a reported Day.js (dayjs) bug — build a minimal failing jest test against the current src, run it across time zones, compare with Moment, check for duplicate issues/PRs, and return a verdict (confirmed, env-dependent, expected behavior, usage error, fixed on dev, duplicate, cannot reproduce). Use when someone gives a dayjs issue number or URL and asks to reproduce, triage, verify, or confirm it, or asks "is this a dayjs bug?" about surprising dayjs output. Not for reviewing PRs, adding features, or writing general tests.
```

**この書き方にした理由**（ユーザーが発火のために打ちそうな言葉）:
> - ライブラリ名を「Day.js (dayjs)」と両方の表記で書きました。ユーザーは `dayjs` と打ちますが、ドキュメントでは Day.js と書かれるからです。
> - issue に対して実際に使われる動詞、*reproduce, triage, verify, confirm* を並べました。issue 番号がなく、意外な出力に驚いているだけの場合（「これって dayjs のバグ？」）も対象にしています。
> - 判定の名前も並べたので、「これは仕様どおり？」という聞き方でも一致します。
> - 最後の文で、最も紛らわしい隣接タスク（PR レビュー、機能追加、一般的なテスト作成）を除外しています。これらも dayjs や issue・PR に触れるので、除外しないと誤発火しかねません。

**本文に書いた判断基準**（曖昧なときにどうするか、何をしてはいけないか）:
> `SKILL.md` の `Decision rules` の内容は次のとおりです。
> - UTC で成功しても諦めない。報告者のタイムゾーンと、落とし穴のあるタイムゾーンをまず試す。
> - dayjs が Moment と同じ結果なら、報告者が意外に感じていても既定の判定は EXPECTED。例外は、暦の計算や ISO の規則として客観的に誤っている場合。
> - npm ビルドでしか再現しなければ FIXED-ON-DEV。修正したコミットを `git log -S` で探す。
> - プラグインの読み込み忘れ、プラグインの順番、フォーマットトークンの誤りは USAGE。正しい呼び方を示す。
> - 既に開いている PR があれば DUPLICATE-OR-HAS-PR。その PR を報告し、競合する修正は書かない。
> - 報告者（やボット）の根本原因の指摘は仮説として扱い、コードを読んで確かめる。
> - 比較対象（Moment など）がなく仕様にも書かれていなければ、どちらかを選ばずに「メンテナーの判断が必要」と書く。
>
> `Do not` の内容: 再現テストが失敗する前に修正を出さない、トリアージ中に `src/` を編集しない、頼まれない限り GitHub に投稿しない、issue に書かれたバージョンを信用しない、`test/__repro__/` をコミットしない。
>
> 決まった作業は、正確なコマンド（`gh issue view <n> -R iamkun/dayjs --comments`、`gh issue list`／`gh pr list` の `--search`、`git log -S`、`TZ=… npx jest … --coverage=false`）で書くか、スクリプトにしてあります。

**補足ファイル**と、本文に入れなかった理由:

| ファイル | 内容 | 分けた理由 |
|---|---|---|
| `references/verdicts.md` | 7つの判定それぞれの使いどころと必要な証拠、判定の優先順位、報告テンプレート | 最後の手順でしか使わない。表とテンプレートだけで SKILL.md の本文とほぼ同じ長さになる |
| `references/timezone-pitfalls.md` | 標準セットの各タイムゾーンを選んだ理由、失敗パターンとその典型的な原因（#3003 の 0 時の欠落など）、`TZ=… node -e` での直接確認の方法 | 結果がタイムゾーンで変わるときや、古い日付・DST 付近の入力でしか使わない。大半の issue では不要 |
| `scripts/new-repro.sh` | `test/__repro__/issue-<n>.test.js` を生成する。`../../src`、プラグイン、`moment` を import し、対照テストも含む | 決まった部分（`src` からの import、MockDate のリセット、Moment との比較）を毎回正しく作れ、定型文にトークンを使わずに済む |
| `scripts/tz-matrix.sh` | 1つのテストファイルを標準の7タイムゾーンと追加分で実行し、PASS/FAIL の表と最初の失敗の詳細を出す | タイムゾーンのループは機械的な作業で、スクリプトにすれば毎回同じ形の表がそのまま報告に使える |


## Part III: テスト

方法: 各プロンプトを **3回ずつ**、**毎回新しいヘッドレスセッション**で実行しました（`claude -p … --output-format stream-json --max-turns 3`、ファイル編集系ツールは禁止）。実行場所は Skill が見つかる assignments リポジトリです。記録に `skill: "dayjs-bug-triage"` の `Skill` ツール呼び出しがあれば「発火」と数えました。スクリプトは `evidence/trigger-run.sh`、結果の生データは `evidence/trigger-results.tsv`（1行1実行、プロンプト文つき）にあります。各実行のターン数・費用・権限拒否の件数は、記録の `result` イベントから抜き出して `evidence/run-results.tsv` に置きました。18回の合計費用は約 $3.08 です。

**発火テスト:**

| プロンプト | 発火すべきか | 結果 |
|---|---|---|
| `dayjs の issue #3239 が再現できるか確認して` | はい | **発火 3/3**。毎回、最初のツール呼び出しが `Skill(dayjs-bug-triage)` |
| `Can you triage this dayjs issue? https://github.com/iamkun/dayjs/issues/3006` | はい | **発火 3/3**。最初のツール呼び出し |
| `dayjs('1981-12-01').daysInMonth() が 1 を返すんだけど、これって dayjs のバグ？`（issue 番号なし） | はい | **発火 3/3**。最初のツール呼び出し |
| `dayjs の PR #3248 をレビューして` | いいえ（紛らわしいもの） | **発火せず 0/3**。毎回 `gh pr view 3248` から始めた。1回は Skill のフォルダを `ls` したが、Skill は読み込まなかった |
| *追加の紛らわしいもの:* `dayjs の timezone プラグインで dayjs.tz() と dayjs.utc() の違いと使い分けを教えて`（同じプラグインの使い方の質問） | いいえ | **発火せず 0/3**。ツールを使わず直接回答した |
| *追加の紛らわしいもの:* `dayjs の calendar プラグインに、週の始まりを月曜にするオプションを追加したい`（未解決のバグがあるプラグインへの機能追加） | いいえ | **発火せず 0/3**。Bash でコードを調べ始めた |

同じプロンプトを Agent ツールの subagent でも試しましたが、**その結果は採用していません**。Skill をセッションの途中で作ったため、subagent に見える Skill 一覧に入っていなかったからです。発火すべきプロンプトでは、subagent はパスからフォルダを見つけて `SKILL.md` を手で読んでいました。紛らわしいプロンプトでは、正しく別の Skill（`code-review`）を選んでいました。ヘッドレスの `claude -p` なら通常どおり Skill を探す新しいセッションになるので、こちらが有効なテストです。

**最初から最後までの実行**と結果:

新しい `claude -p` セッションで実行しました。プロンプトは `dayjs の issue #3239 が再現できるか確認して。dayjs のチェックアウトは <scratch>/dayjs にあります（npm ci 済み）。` です。#3239 は、私が手作業でトリアージしていない issue です。

権限は、読み取り系の `gh`、`git log/show`、`jest`、`node`、Skill のスクリプト、clone 内への書き込みだけに絞ったので、GitHub への投稿はできない状態でした。35ターンで、費用は $0.67 でした（`evidence/run-results.tsv`）。ツール呼び出しの全記録は `evidence/e2e-3239-tool-calls.txt`、報告の全文は `evidence/e2e-3239-report.md`、作成された再現テストは `evidence/issue-3239.test.js` にあります。

```
ツール呼び出しの流れ（要約）:
  Skill(dayjs-bug-triage) → gh issue view 3239 --comments → git log -1（コミットを記録）
  → new-repro.sh / tz-matrix.sh / verdicts.md を Read → test/__repro__/issue-3239.test.js を Write
  → gh issue list / gh pr list --search "customParseFormat week utc"
  → 7つのタイムゾーンで TZ=<zone> npx jest … → gh pr view 3240 / gh pr diff 3240

報告（要約。原文は evidence/e2e-3239-report.md）:
  ## Triage: iamkun/dayjs#3239 — dayjs.utc() で customParseFormat の週トークン（w/ww）が無視される
  判定: 再現した。ただし修正 PR #3240 が既にあるため DUPLICATE-OR-HAS-PR
  検証環境: dayjs 436bde0（dev）、Node v24.21.0、Moment 2.29.2

  | TZ                 | utc（報告の主張） | ローカル（対照） | dayjs.utc             | moment.utc            |
  | UTC                | ✕                | ✓               | 2024-01-01T00:00:00Z  | 2024-07-28T00:00:00Z  |
  | Asia/Tokyo … America/Sao_Paulo（他6つ） | ✕ | ✓          | 同上                   | 同上                   |
  → 7つすべてで失敗。タイムゾーンに依存しないロジックのバグ。

  原因: 報告者の分析は正しい。src/plugin/customParseFormat/index.js:202-204 の
  `if (utc)` 分岐が、パースした `week` を使う前に return している。
  週を反映する処理（207-209行）はローカル時刻の分岐にしかない。
  補足: 報告のコードで 'ww' を出力するには advancedFormat も必要。
  ローカル時刻のパースでは dayjs が月曜 07-29、Moment が日曜 07-28 を返す（週番号はどちらも31）。これは別の論点。
  既存の対応: PR #3240（open、マージ可能）が同じ根本原因を修正している。#2632/#2709/#2827 は関連するが別件（ISO 週のパース）。
  次のステップ: PR #3240 のレビューとマージを待つ。トリアージ中に src/ は編集していない。
```

結果は私自身でも確認しました。
- clone で `git status` を実行すると `?? test/__repro__/` だけで、`src/` は変更されていません。
- `customParseFormat/index.js` の202〜209行は、原因の説明と一致します。
- PR #3240（"fix(customParseFormat): apply the week token when parsing in UTC mode"、OPEN）は実在します。

実行は判断ルールどおりでした。`src` に対して再現し、Moment と比べ、7つのタイムゾーンすべてを試してからタイムゾーンに依存しないと結論し、既存の PR を見つけ、競合する修正は書かずに止まりました。

一つ荒い点として、権限の拒否が7件ありました。すべて私のテスト環境の許可リストが狭すぎたためで、Skill の問題ではありません。原因は、`cd … &&` のような複合コマンド、`bash <script>` という呼び方、そして `.claude/skills/…` の symlink 側のパスが、許可した `week3/…` のパスと一致しなかったことです。`tz-matrix.sh` が拒否されたあとも、エージェントはタイムゾーンごとに `npx jest` を実行する同じ処理で代替し、表を完成させていました。この影響で、Skill の手順から外れた点が2つあります。1つ目は、`new-repro.sh` を読んだうえで、スクリプトを実行せずにテストファイルを手で書いたことです。2つ目は、追加しようとしたタイムゾーン（`Europe/Is…`、ツール呼び出し記録の21行目）が代替のループでは抜け落ち、標準の7つだけが実行されたことです。
