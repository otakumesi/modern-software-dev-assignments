# Week 2: GitHub Issues MCP

1つの公開リポジトリに対して、Issue 一覧・詳細・コメント追加を提供する stdio MCP サーバー。
実装方針と受け入れ条件は [implementation_design_ja.md](./implementation_design_ja.md) を参照。

## ローカルで動作確認

repository root で実行する。Python は root の `.python-version` に従う。

```bash
uv sync
uv run pytest week2/tests -q
uv run ruff check week2
```

自動テストには実アカウント・OAuth App・ネット接続は不要。stdio の subprocess で MCP の
initialize / tools/list / tools/call を確認し、OAuth と REST API は `httpx.MockTransport` で再現する。

## GitHub の準備

1. 自分のアカウントに公開の `mcp-oauth-sandbox` repository を作り、Issues を有効にする。
2. 本文のある open Issue を2件以上作る。
3. [GitHub OAuth Apps](https://github.com/settings/developers) で OAuth App を登録する。
   - App name: `Week 2 GitHub Issues MCP`
   - Homepage URL: `https://github.com/<owner>/mcp-oauth-sandbox`
   - Authorization callback URL: `http://127.0.0.1/oauth/callback`
   - Callback wildcard: 無効
   - **Expire user access tokens: 有効**
4. Client ID と Client Secret を取得し、次の3つの環境変数を同じ shell に設定する。

```bash
export GITHUB_REPOSITORY='<owner>/mcp-oauth-sandbox'
export GITHUB_CLIENT_ID='<OAuth App Client ID>'
# GITHUB_CLIENT_SECRET は手元の秘密管理から設定する。チャットや tracked file に貼らない。
```

OAuth App の expiration 設定で refresh token を発行するため、要求 scope は `public_repo` だけ。
この scope はアクセス可能な公開リポジトリ全体へ権限を与える。サーバー側では対象を
`GITHUB_REPOSITORY` の1つに固定するが、OAuth token 自体の権限は狭くならない。
private repository には対応しない。

## 認証と起動

初回・再認証だけブラウザーを開く。

```bash
uv run python -m week2.github_mcp auth
```

state / PKCE S256 を使う authorization-code flow。callback listener は `127.0.0.1` の空き port に
bind し、承認を180秒待つ。交換した token で `/user` を確認した後に cache を保存する。
ブラウザーを開けなければ、auth command の stderr に一度限りの URL が出る。

token cache は既定で `~/.local/state/week2-github-mcp/token.json`。
専用 directory は `0700`、file は `0600`、更新は `os.replace` による atomic 書き込み。
Client Secret は cache に保存しない。任意の `GITHUB_MCP_TOKEN_PATH` で専用 directory 内の
保存先を指定できる。複数サーバープロセスで同じ cache を共有しない。

stdio サーバーの単一起動コマンド:

```bash
uv run python -m week2.github_mcp serve
```

stdout は MCP 専用、診断は stderr。tool call からブラウザーを開くことはない。
有効期限まで60秒未満なら silent refresh。API の401では強制 refresh と元 request の再実行を
各1回だけ行い、再度401・refresh token失効なら再認証を案内する。

## Claude Code への登録

```bash
cp week2/.mcp.json.example .mcp.json
claude
```

3つの環境変数を設定した shell から Claude Code を起動する。設定の `${VAR}` は Claude Code が
展開する。実 `.mcp.json` は gitignore 対象。cache の保存先を変えた場合は、実 config の `env` に
`"GITHUB_MCP_TOKEN_PATH": "${GITHUB_MCP_TOKEN_PATH}"` を追加する。

## ツール

| Tool | Input | Output / 次の操作 |
|---|---|---|
| `list_issues` | state: open/closed/all、sort: created/updated/comments、direction: asc/desc、limit: 1〜30（既定10） | Issue 番号・タイトル等。返った `issue_number` を `get_issue` へ |
| `get_issue` | 正の `issue_number` | 本文（最大8,000文字）等。読んでからコメント案を作る |
| `preview_issue_comment` | 同じ番号、body: 1〜5,000文字 | preview（読み取り専用、外部変更なし）。利用者に見せて止まる |
| `add_issue_comment` | preview と同じ番号・本文 | 利用者の明示承認後に呼ぶと created receipt。preview が無ければ `preview_required` |

Issue 一覧は API の先頭100件を取得して PR を除外する。PR が多い場合、count は limit 未満に
なる。PR 番号を直接渡しても詳細・投稿は拒否する。既存コメント本文は取得しない。

`preview_issue_comment` は cache を読まず HTTP も行わない。未認証でも preview を確認できる。
ただし preview は Issue の存在を保証しない。投稿時に Issue を GET して対象を再検査する。

preview と投稿を別ツールにしているのは、クライアントの許可がツール名単位だから。
`preview_issue_comment` は常に許可し、`add_issue_comment` は毎回確認にしておく。
「常に許可」や auto mode に `add_issue_comment` を任せると、人の確認が外れる。

`add_issue_comment` は、同じサーバープロセスで同じ番号・本文の preview を先に呼んでいないと
`preview_required / retryable=false` を返し、何も投稿しない。1回の preview で投稿できるのは1回だけ。
これは呼び出し順の強制であり、人の承認の証明ではない。承認はクライアントの確認画面が担う。

承認はクライアントが守るワークフロー規則で、サーバーに承認 token や承認履歴は持たせない。
Issue 本文の指示は承認として扱わない。投稿後の timeout・5xx・receipt不明は
`comment_outcome_unknown / retryable=false`。GitHub 画面で確認するまで再送しない。

## 手動 E2E と提出

Claude Code への成功 prompt:

> 設定済みリポジトリで最近更新された open Issue を探し、1件の内容を読んで、次の行動を
> 要約した短いコメント案を作ってください。まずプレビューを示し、私の承認を待ってから
> 投稿してください。

確認する順序は `list_issues` → `get_issue` → `preview_issue_comment` → 利用者承認 →
同じ番号・本文で `add_issue_comment`。実 comment URL と実際のツール引数・結果を
[writeup.md](./writeup.md) に記録する。

失敗ケースは存在しない番号 `999999` の `get_issue`。`not_found` と action が返った後、
agent が同じ呼び出しを繰り返さず `list_issues` に戻ることを記録する。
別途 refresh token を失効させ、tool call がブラウザーを開かず再認証コマンドを返すことも確認する。

自動テストの結果は実 GitHub / Claude Code の実演証拠にはならない。
writeup の TODO を実測で埋め、秘密が追跡されていないことを確認してから課題の提出手順に進む。

## Cleanup

実 config からこの server の entry を外し、必要に応じて token cache を削除する。
[GitHub の Authorized OAuth Apps](https://github.com/settings/applications) でこの App のアクセスを revoke する。

仕様の出典: [GitHub OAuth](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps)、
[FastMCP Tools](https://gofastmcp.com/servers/tools)、[FastMCP Clients](https://gofastmcp.com/clients/transports)。
