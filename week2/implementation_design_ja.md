# Week 2 GitHub Issues MCP 実装設計

- 状態: 採用
- 作成日: 2026-09-29
- 対象課題: [assignment.md](./assignment.md)
- 実装開始条件: 本書の受け入れ条件を維持したまま実装すること

## 1. 結論

Week 2 では、**1つの FastMCP サーバーから GitHub Issues 用の3ツールを提供する**。

1. `list_issues`: Issue の候補を一覧する読み取りツール
2. `get_issue`: 選んだ Issue の本文を読む読み取りツール
3. `add_issue_comment`: Issue にコメントを追加する書き込みツール

標準ワークフローは次の順序に固定する。

```text
list_issues
    ↓ issue_number
get_issue
    ↓ 同じ issue_number と、内容を読んで作った body
add_issue_comment(dry_run=true)
    ↓ プレビューを利用者が明示承認
add_issue_comment(dry_run=false)
```

API は GitHub REST API、認証は **GitHub OAuth App の Web Application Flow
(Authorization Code Flow)** を使う。OAuth 認証自体は MCP ツールにしない。初回認証は
`auth` CLI、MCP サーバーは `serve` CLI として分離する。

```bash
# 初回認証・再認証。このコマンドだけがブラウザーを開く
uv run python -m week2.github_mcp auth

# MCP クライアントが stdio サーバーとして起動する単一コマンド
uv run python -m week2.github_mcp serve
```

この選択は、課題の「3つ以上の合成可能なツール」「実状態を変更する書き込みツール」
「OAuth の code exchange・キャッシュ・silent refresh」「stdio」「プロトコル試験」を、
小さく確認しやすい構成で同時に満たす。

## 2. 採用理由と不採用案

### 2.1 GitHub Issues を選ぶ理由

- Issue 番号がツール間で自然に受け渡せるため、合成を明確に実演できる。
- コメント投稿は結果を GitHub 画面で確認でき、実際の write を証明しやすい。
- 読み取り2個と書き込み1個だけで、実用的な一連の仕事になる。
- OAuth の期限切れ access token と refresh token を GitHub 公式仕様で扱える。
- 普段使う GitHub 上で、成功結果・失敗結果・URL を write-up に残しやすい。

### 2.2 認証方式の判断

| 案 | 判断 | 理由 |
|---|---|---|
| GitHub OAuth App + Web Application Flow | 採用 | 課題が求める authorization-code exchange と refresh を直接、少ない構成要素で実装できる |
| GitHub App | 不採用 | リポジトリ単位の権限は優れるが、App のインストールと権限管理が今回の学習範囲を広げる |
| Device Flow | 不採用 | CLI には適するが、今回はローカル callback を含む標準的な code exchange を明示的に実装する |
| Personal Access Token | 不採用 | 貼り付けた bearer token であり、課題の OAuth 要件を満たさない |

GitHub は GitHub App の利用も推奨しているが、今回は「OAuth を内包する小さな MCP」として
OAuth App を選ぶ。これは単純さを優先した課題用の判断であり、実運用製品の一般的な推奨ではない。

### 2.3 参考 MCP サーバーから採用する考え方

実装前の参考サーバーとして、公式の
[Filesystem MCP Server](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem)
を確認した。次の3点を本設計へ取り込む。

- 操作対象を明示的な許可範囲に閉じ込める。本サーバーでは対象リポジトリを設定で1つに固定する。
- 読み取り・書き込み・冪等性・外部アクセスを tool annotations で示す。
- 書き込み前に dry-run のプレビューを返す。

## 3. スコープと安全境界

### 3.1 対象リポジトリ

実演専用の公開リポジトリ `mcp-oauth-sandbox` を利用者の GitHub アカウント配下に作り、
Issue を有効にする。MCP が操作するリポジトリは環境変数で固定する。

```text
GITHUB_REPOSITORY=<owner>/mcp-oauth-sandbox
```

各ツールに `owner` や `repo` 引数は持たせない。これにより、モデルが別のリポジトリ名を
生成して誤操作する経路をなくす。起動時に値が厳密に `owner/name` 形式か検証し、空値や
余分なパスを拒否する。

OAuth App の `public_repo` はアカウントがアクセスできる公開リポジトリ全体に対して広い
権限を持つ。コード内の固定リポジトリはこの権限自体を狭めるものではないため、残余リスクを
明記する。実演は専用リポジトリだけで行い、token をリポジトリ外に保存し、漏えい時は GitHub
から直ちに revoke する。

### 3.2 対象に含めるもの

- 公開リポジトリの通常の Issue 一覧
- 1件の Issue の詳細取得
- Issue コメントのプレビューと新規投稿
- OAuth の初回認証、token キャッシュ、期限前 refresh、再認証案内
- Claude Code への stdio 登録
- 自動試験と実 GitHub での手動 E2E 実演

### 3.3 対象に含めないもの

- 複数ユーザー、複数リポジトリ、private repository
- Pull Request の取得やレビューコメント
- Issue の作成、編集、close、削除
- コメントの編集、削除
- GitHub App、webhook、remote HTTP transport、Web UI
- MCP resources、prompts、バックグラウンドジョブ
- DB、汎用 provider 抽象化、OAuth SDK
- 複数プロセスが同じ token cache を同時利用する構成
- 100件を超える完全なページネーション

## 4. 外部設定と起動契約

### 4.1 必須環境変数

| 変数 | 用途 | 秘密か | 検証タイミング |
|---|---|---:|---|
| `GITHUB_CLIENT_ID` | OAuth App の Client ID | いいえ | `auth` と認証済み API 呼び出し時 |
| `GITHUB_CLIENT_SECRET` | code exchange / refresh | はい | `auth` と refresh 時 |
| `GITHUB_REPOSITORY` | 許可する唯一の `owner/repo` | いいえ | `auth` / `serve` 起動時 |

任意の `GITHUB_MCP_TOKEN_PATH` で cache の位置を上書きできる。未指定時は
`~/.local/state/week2-github-mcp/token.json` を使う。

`serve` は `GITHUB_REPOSITORY` が不正なら stderr に短い理由を出して起動を失敗させる。
Client ID / secret は、tool 一覧や `dry_run=true` だけなら不要なので遅延検証する。

### 4.2 stdio の規則

- `serve` は FastMCP の標準 stdio transport で起動する。
- stdout は MCP の JSON-RPC 専用とする。
- 診断ログは stderr にだけ出す。
- token、authorization code、state、PKCE verifier、`Authorization` header をログに出さない。
- 1つの文書化された起動コマンドでサーバーを起動できるようにする。

## 5. MCP ツール契約

### 5.1 共通原則

- 入力制約は docstring だけでなく JSON Schema に表現する。
- Pydantic model を戻り値に使い、FastMCP に `outputSchema` と
  `structuredContent` を生成させる。
  FastMCP 4 は union 型を `result` に包むため、`TypeAdapter` から生成した schema に
  トップレベル `type="object"` を指定して登録し、`status` をトップレベルに維持する。
- GitHub の raw JSON は返さない。
- 日時は GitHub が返す ISO 8601 UTC 文字列を使う。
- `issue_number` は GitHub の内部 `id` ではなく、リポジトリ内の `number` とする。
- 既知の API・認証・ネットワーク失敗は traceback ではなく構造化データで返す。
- 入力 schema 違反は FastMCP / Pydantic の MCP validation error に任せる。

response は曖昧な optional field の集合にせず、`status` を discriminator にした Pydantic
model の union とする。

| response | 成功・プレビュー variant | 失敗 variant |
|---|---|---|
| `ListIssuesResponse` | `status="ok"`, `repository`, `count`, `issues` | `status="error"`, `repository`, `error` |
| `GetIssueResponse` | `status="ok"`, `repository`, `issue` | `status="error"`, `repository`, `issue_number`, `error` |
| `AddIssueCommentResponse` | `status="preview"` または `status="created"` と各 receipt field | `status="error"`, `repository`, `issue_number`, `error` |

共通の `error` model は `code`、`message`、`retryable`、`action` と、任意の
`http_status`、`retry_after_seconds` だけを持つ。

GitHub payload の nullable / nested field は次のように正規化する。

- 削除済み user などで `user` が null の場合、`author` は null にする。
- `body` が null の場合は空文字にし、切り詰めた場合だけ `body_truncated=true` にする。
- label は `name` の文字列だけ、assignee は `login` の文字列だけを残す。
- agent が開く URL には API URL ではなく `html_url` を使う。
- GitHub が追加した未知の field は無視し、MCP の出力契約へ漏らさない。

### 5.2 `list_issues`

目的: 対象リポジトリから、次のツールへ渡す Issue 番号を取得する。

```python
list_issues(
    state: Literal["open", "closed", "all"] = "open",
    sort: Literal["created", "updated", "comments"] = "updated",
    direction: Literal["asc", "desc"] = "desc",
    limit: Annotated[int, Field(ge=1, le=30)] = 10,
) -> ListIssuesResponse
```

GitHub の Issue endpoint は Pull Request も返すため、`pull_request` key を持つ要素を除外する。
1回の API request で最大100件を取得し、PR 除外後の先頭 `limit` 件だけを返す。
そのため、PR が多い場合の `count` は `limit` 未満になり得る。

成功時の出力:

```json
{
  "status": "ok",
  "repository": "owner/mcp-oauth-sandbox",
  "count": 1,
  "issues": [
    {
      "issue_number": 12,
      "title": "Document retry behavior",
      "state": "open",
      "author": "octocat",
      "labels": ["documentation"],
      "comment_count": 2,
      "updated_at": "2026-09-29T12:00:00Z",
      "url": "https://github.com/owner/mcp-oauth-sandbox/issues/12"
    }
  ]
}
```

含めない主な raw field は、node ID、API URL 群、avatar、reactions、permissions、timeline、
body である。本文は候補一覧には重いため、`get_issue` だけで返す。

docstring には「返された `issue_number` をそのまま `get_issue` または
`add_issue_comment` に渡す」「PR は含まない」と記載する。

Annotations:

| Hint | 値 | 理由 |
|---|---:|---|
| `readOnlyHint` | `true` | 外部状態を変更しない |
| `openWorldHint` | `true` | GitHub という外部世界へアクセスする |

`destructiveHint` と `idempotentHint` は read-only tool では意味を持たないため省略する。

### 5.3 `get_issue`

目的: 一覧で選んだ Issue の内容を読み、コメント案を作れる情報を得る。

```python
get_issue(
    issue_number: Annotated[int, Field(ge=1)],
) -> GetIssueResponse
```

`issue_number` の schema description に「`list_issues` が返した正の整数であり、GitHub の
グローバル ID ではない」と入れる。取得結果が Pull Request だった場合は通常 Issue として
扱わず、`unsupported_target` を返す。

成功時の `issue` field:

```json
{
  "issue_number": 12,
  "title": "Document retry behavior",
  "state": "open",
  "state_reason": null,
  "author": "octocat",
  "assignees": ["hubot"],
  "labels": ["documentation"],
  "body": "Issue body...",
  "body_truncated": false,
  "comment_count": 2,
  "locked": false,
  "created_at": "2026-09-28T10:00:00Z",
  "updated_at": "2026-09-29T12:00:00Z",
  "url": "https://github.com/owner/mcp-oauth-sandbox/issues/12"
}
```

Issue 本文は最大8,000文字で切り、切った場合は `body_truncated=true` にする。API の raw
payload、既存コメント本文、ユーザー profile は返さない。

docstring には「番号は `list_issues` から取得する」「コメント案を作る前に呼ぶ」と記載する。
Annotations は `list_issues` と同じ `readOnlyHint=true`、`openWorldHint=true` にする。

### 5.4 `add_issue_comment`

目的: コメントをまずプレビューし、利用者の承認後だけ実際に投稿する。

```python
add_issue_comment(
    issue_number: Annotated[int, Field(ge=1)],
    body: Annotated[str, Field(min_length=1, max_length=5000)],
    dry_run: bool = True,
) -> AddIssueCommentResponse
```

`body` の1〜5,000文字という制約は JSON Schema に出す。`dry_run=true` は既定値であり、token
cache を読まず、OAuth を要求せず、HTTP request も行わない。固定リポジトリ、番号、本文、
投稿先 URL のプレビューだけを返す。

```json
{
  "status": "preview",
  "repository": "owner/mcp-oauth-sandbox",
  "issue_number": 12,
  "body": "I will add a retry example.",
  "target_url": "https://github.com/owner/mcp-oauth-sandbox/issues/12"
}
```

`dry_run=false` のときだけ、最初に Issue を GET して存在と「PR ではないこと」を確認し、
続けて comment endpoint に POST する。成功時は receipt に必要な field だけを返す。

```json
{
  "status": "created",
  "repository": "owner/mcp-oauth-sandbox",
  "issue_number": 12,
  "comment_id": 123456,
  "author": "octocat",
  "created_at": "2026-09-29T12:05:00Z",
  "url": "https://github.com/owner/mcp-oauth-sandbox/issues/12#issuecomment-123456"
}
```

docstring には次を明記する。

- 既定は preview である。
- preview を利用者へ示し、明示承認後に同じ `issue_number` と `body` を
  `dry_run=false` で再実行する。
- 投稿により GitHub 通知が発生し得る。
- 明示的な 401 response を refresh した直後の1回を除き、同じ投稿を自動再試行しない。
  特に結果が不明な失敗は、GitHub 画面で確認するまで再送しない。

Annotations:

| Hint | 値 | 理由 |
|---|---:|---|
| `readOnlyHint` | `false` | `dry_run=false` は GitHub を変更する |
| `destructiveHint` | `false` | 追加操作であり、既存データを削除・上書きしない |
| `idempotentHint` | `false` | 同じ POST を繰り返すと重複コメントになる |
| `openWorldHint` | `true` | GitHub という外部世界へアクセスする |

tool annotation はクライアントへの hint であって強制機構ではない。実際の brake は
schema の既定値 `dry_run=true` と、`false` のときだけ POST するコードで実装する。

## 6. サーバー全体の instructions

`FastMCP(name=..., instructions=...)` に、ツールを横断する次の規則を日本語ではなく短い英語で
入れる。モデルへの契約なので、実装の内部説明は含めない。

```text
This server operates only on the configured GitHub repository.
For comments, call list_issues, then get_issue with the returned issue_number.
Call add_issue_comment with dry_run=true and show the exact preview to the user.
Use dry_run=false only after explicit user approval, with the same issue_number and body.
Never invent an issue_number. Follow error.retryable and error.action.
Never automatically retry a created comment or a comment_outcome_unknown result.
If authentication is required, tell the user to run the reported auth command;
do not retry the tool or attempt to open a browser.
```

この順序は instructions と各 tool の docstring の両方で整合させる。schema、docstring、
instructions の既定値や上限が食い違わないことをテストする。

## 7. 構造化エラー

既知の運用失敗は各 response の `status="error"` と `error` object で返す。

```json
{
  "status": "error",
  "repository": "owner/mcp-oauth-sandbox",
  "error": {
    "code": "not_found",
    "message": "Issue #999999 was not found in the configured repository.",
    "retryable": false,
    "http_status": 404,
    "retry_after_seconds": null,
    "action": "Call list_issues and use an issue_number returned by it."
  }
}
```

`message` は token、secret、authorization code、raw response body を含めない。

| code | 主な原因 | retryable | action |
|---|---|---:|---|
| `auth_required` | cache がない | `false` | auth command を実行し、MCP 接続を再起動 |
| `reauth_required` | refresh token が失効・拒否された | `false` | auth command で再認証し、MCP 接続を再起動 |
| `configuration_error` | OAuth 用環境変数が不足 | `false` | 設定を直して MCP 接続を再起動 |
| `auth_unavailable` | refresh endpoint の一時的な通信・5xx | `true` | 後で元の読み取りまたは安全な call を再実行 |
| `insufficient_scope` | token に `public_repo` がない | `false` | OAuth 設定を確認して再認証 |
| `forbidden` | scope、権限、リポジトリ設定が不足 | `false` | OAuth scope と対象 repo の権限を確認 |
| `not_found` | Issue 番号が存在しない | `false` | `list_issues` から番号を選び直す |
| `unsupported_target` | 番号が Pull Request を指す | `false` | `list_issues` が返した通常 Issue を使う |
| `rate_limited` | primary / secondary rate limit | `true` | 指定秒数待ってから読み取りを再試行。書き込み結果不明なら再試行しない |
| `github_rejected` | 410、422 など request を GitHub が拒否 | `false` | message に従い入力または Issue 状態を修正 |
| `network_error` | GET 前後の接続・timeout | `true` | 後で読み取りを再試行 |
| `github_unavailable` | GET に対する GitHub 5xx | `true` | 後で読み取りを再試行 |
| `comment_outcome_unknown` | POST 送信後の timeout、切断、曖昧な 5xx | `false` | GitHub 画面で投稿有無を確認。自動再試行しない |

追加の変換規則:

- 401 を受けたら token を強制 refresh し、元の request を1回だけ再実行する。
- その1回も 401 なら `reauth_required` にする。ブラウザーは開かない。
- 403 / 429 で `Retry-After` または rate-limit header が示される場合は
  `rate_limited`、それ以外の 403 は `forbidden` にする。
- 404 は `not_found`、410 / 422 は `github_rejected` にする。
- GET は失敗が明確なので `retryable=true` を返せる。
- POST の 401 response は未認証として処理されており書き込み未成立なので、refresh 後の1回だけ
  再送してよい。それ以外の POST の timeout / 5xx は成立有無を断定せず再送しない。
- 予期しない programming error は隠さずサーバーエラーとして stderr に記録するが、秘密値は
  redact する。

## 8. OAuth 設計

### 8.1 OAuth App の設定

- App 種別: GitHub OAuth App
- App name: `Week 2 GitHub Issues MCP`
- Homepage URL: `https://github.com/<owner>/mcp-oauth-sandbox`
- callback URL: `http://127.0.0.1/oauth/callback`
- callback wildcard: 無効
- 実行時 listener: `127.0.0.1` の OS が選んだ空き port
- 実行時 redirect URI: `http://127.0.0.1:<port>/oauth/callback`
- access token の expiration: 有効
- 要求 scope: `public_repo`

GitHub は loopback callback について登録値と異なる実行時 port を許可している。`localhost`
ではなく loopback literal `127.0.0.1` を使い、外部 interface へ bind しない。

scope の根拠:

| scope | 必要性 |
|---|---|
| `public_repo` | 専用の公開リポジトリで Issue を読み、comment を書くため。OAuth App でこの write を可能にする最小の repository scope |

`repo` は private repository まで広げるため要求しない。profile、email、organization、gist、
workflow 等の scope も要求しない。OAuth App 側で expiring access tokens を有効にすると refresh
token が発行されるため、同じ効果を個別認証で要求する特殊な `offline_access` も重ねて要求しない。
code exchange の response に refresh token と両方の有効期限がなければ設定誤りとして cache
せず、expiration 設定を確認するよう案内する。

### 8.2 初回認証フロー

```text
利用者
  │ uv run python -m week2.github_mcp auth
  ▼
ローカル callback listener を 127.0.0.1:<ephemeral-port> で開始
  │ state と PKCE verifier/challenge(S256) を生成
  ▼
既定ブラウザーで github.com/login/oauth/authorize を開く
  │ 利用者が GitHub 上で承認
  ▼
callback で code と state を受信
  │ state を定数時間比較し、不一致なら中止
  ▼
code + 同じ redirect_uri + PKCE verifier + client secret を token endpoint へ送る
  │ access token / refresh token / 有効期限を受信
  ▼
GET /user で認証ユーザーを再検証
  │ token pair を安全に atomic 保存
  ▼
ユーザー名と対象 repo だけを表示して終了
```

- `state` と PKCE S256 を両方必須にする。
- authorization code の待機は180秒で timeout する。
- browser 起動に失敗した場合は URL を表示して手動で開けるようにする。
- この一度限りの authorization URL には state と PKCE challenge が含まれる。表示を許すのは
  standalone の `auth` command だけとし、file や通常 log へ保存せず、`serve` からは出さない。
- callback HTML には成功・失敗の短い表示だけを出し、code や token を埋め込まない。
- state 不一致、OAuth error、timeout では cache を作成・更新しない。
- token response の granted scope に `public_repo` があることを確認し、不足時は cache しない。
- code exchange 成功後は GitHub の推奨どおり `/user` で account を検証する。

### 8.3 token cache

保存する field:

```json
{
  "access_token": "<redacted>",
  "refresh_token": "<redacted>",
  "access_token_expires_at": 1790683200,
  "refresh_token_expires_at": 1806321600,
  "scope": ["public_repo"],
  "login": "octocat"
}
```

- Client secret、authorization code、state、PKCE verifier は保存しない。
- parent directory は mode `0700`、file は `0600` にする。
- 一時 file を同じ directory に `0600` で書き、flush 後に `os.replace` で atomic 更新する。
- JSON が壊れている、必要 field がない、permission が安全でない場合は token として使わず、
  `reauth_required` を返す。
- `.mcp.json` とは別にし、既定では repository の外に置く。

### 8.4 silent refresh

API request の前に access token の期限を確認し、期限まで60秒未満なら silent refresh する。

1. process-local の `asyncio.Lock` を取る。
2. lock 後に cache を再読込し、別 coroutine が既に更新していないか確認する。
3. `grant_type=refresh_token` で token endpoint を呼ぶ。
4. GitHub が返した新しい access token と新しい refresh token を1組として atomic 保存する。
5. lock を解放し、新しい access token で API request を続ける。

GitHub は refresh 時に古い access token と refresh token を無効化するため、新旧 token を
混ぜて保存しない。invalid / expired refresh token は `reauth_required`、一時的な通信失敗や
token endpoint の 5xx は `auth_unavailable`、Client ID / secret 不足は
`configuration_error` とする。どの場合も auth CLI を内部起動したりブラウザーを開いたり
しない。

### 8.5 実行中の 401

期限計算より前に revoke された場合に備え、API の 401 を検出する。401 ごとに無制限に
refresh せず、1 request につき「強制 refresh 1回、元 request の再実行1回」だけにする。
再度 401 なら `reauth_required` で終了する。

## 9. GitHub REST client

- HTTP client: 共有する `httpx.AsyncClient`
- API base: `https://api.github.com`
- request timeout: 10秒
- 自動 retry: なし
- `Accept`: `application/vnd.github+json`
- `X-GitHub-Api-Version`: `2026-03-10`
- `User-Agent`: `week2-github-issues-mcp`
- 認証: `Authorization: Bearer <token>`

使用 endpoint:

| 操作 | method / path |
|---|---|
| token 所有者確認 | `GET /user` |
| Issue 一覧 | `GET /repos/{owner}/{repo}/issues` |
| Issue 詳細と write 前検査 | `GET /repos/{owner}/{repo}/issues/{issue_number}` |
| コメント追加 | `POST /repos/{owner}/{repo}/issues/{issue_number}/comments` |

`httpx` の request / response debug logging は無効にする。GitHub response は client 層で
response model に正規化し、MCP tool から raw JSON を直接返さない。

## 10. ファイル構成

実装時の最小構成を次に固定する。

```text
week2/
├── __init__.py
├── github_mcp.py                 # CLI、FastMCP、schema、3 tool
├── github_client.py              # OAuth、cache、refresh、REST client、error変換
├── tests/
│   ├── test_mcp_protocol.py      # stdio subprocessを通るMCP試験
│   └── test_github_client.py     # MockTransportによるOAuth/API試験
├── .mcp.json.example             # 秘密を含まない登録例
├── README.md                     # setup、auth、serve、test、cleanup
└── writeup.md                    # 実測した提出用記録
```

責務を2つの source file にだけ分ける。repository pattern、provider interface、service layer、
DI container、独自 retry framework は作らない。Pydantic response model は tool 契約の近くに
置き、HTTP と token の処理だけ `github_client.py` に隔離する。

root の `pyproject.toml` / `uv.lock` を既存プロジェクトの唯一の依存管理として使う。
実装時に次だけを変更する。

- runtime dependency に `fastmcp>=4,<5` と `httpx` を置く。
- dev dependency に `pytest-asyncio` を追加する。
- `.gitignore` に exact name `.mcp.json` を追加する。

別の `week2/pyproject.toml`、Poetry 設定、OAuth library、`platformdirs` は追加しない。
現在ある Week 1 や利用者の未 commit 変更には触れない。

## 11. `.mcp.json.example` と秘密管理

example は `github-issues-week2` という stdio server を登録し、次の内容だけを示す。

- type: `stdio`
- command: `uv`
- args: `--directory ${CLAUDE_PROJECT_DIR:-.} run python -m week2.github_mcp serve`
- Claude Code の `${VAR}` 展開で3つの必須環境変数を引き継ぐ

commit する example の形は次で固定する。

```json
{
  "mcpServers": {
    "github-issues-week2": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "--directory",
        "${CLAUDE_PROJECT_DIR:-.}",
        "run",
        "python",
        "-m",
        "week2.github_mcp",
        "serve"
      ],
      "env": {
        "GITHUB_CLIENT_ID": "${GITHUB_CLIENT_ID}",
        "GITHUB_CLIENT_SECRET": "${GITHUB_CLIENT_SECRET}",
        "GITHUB_REPOSITORY": "${GITHUB_REPOSITORY}"
      }
    }
  }
}
```

example を repository root の `.mcp.json` にコピーして使う。3つの環境変数は `auth` command と
Claude Code を起動する前に同じ shell で export する。Claude Code は未設定の `${VAR}` がある
config を parse error にするため、欠落を起動前に検出できる。
`${CLAUDE_PROJECT_DIR:-.}` は Claude Code 公式の project-root fallback であり、
`uv --directory` へ渡して subprocess の working directory を repository root に固定する。
example に実値を入れない。実 root `.mcp.json` は課題指定どおり gitignore し、cache は repo 外に
置く。commit 前に tracked files を対象に token prefix、Client Secret、実 `.mcp.json` がないことを
確認する。cache path を変える利用者だけが real config の `env` に
`GITHUB_MCP_TOKEN_PATH` を追加する。

## 12. テスト設計

自動試験は実 GitHub へ接続せず、実状態を変更しない。

### 12.1 必須の MCP protocol test

`test_mcp_protocol.py` は Python 関数を直接呼ばず、FastMCP client の `StdioTransport` から
次の subprocess を起動する。
client は `mode="legacy"` を指定し、`server/discover` の新方式ではなく課題で検証する
`initialize` handshake を実行する。

```text
<test-python> -m week2.github_mcp serve
```

環境には dummy の固定 repository と一時 token path を渡す。試験内容:

1. MCP initialize を完了する。
2. `tools/list` で tool がちょうど3つあることを確認する。
3. tool 名、description、input schema の enum / minimum / maximum / default、annotations、
   output schema を確認する。
4. `tools/call` で `add_issue_comment(dry_run=true)` を呼び、`status=preview` と整形済み
   structured content を確認する。
5. cache file が作られず、HTTP も OAuth も不要だったことを確認する。
6. `limit=31` が MCP validation error になることを確認する。

これにより「関数の unit test」ではなく、stdio と MCP protocol を実際に通った証拠にする。

### 12.2 REST / OAuth unit test

`httpx.MockTransport` と一時 directory を使い、少なくとも次を検証する。

- Issue と PR が混在する raw response から PR を除き、必要 field だけを返す。
- null の `body` を空文字、null の `user` を `author=null` に正規化する。
- 本文を8,000文字で切り、`body_truncated` を正しく設定する。
- 404 が `not_found / retryable=false / actionあり` になる。
- PR 番号が `unsupported_target` になる。
- `dry_run=true` は cache access と HTTP request が0回である。
- comment 201 が `created` receipt になり、POST は1回だけである。
- POST 後の timeout / 5xx が `comment_outcome_unknown` となり、自動再送しない。
- 期限前60秒で refresh し、新しい token pair を同時保存する。
- 401 で強制 refresh と元 request の再実行をそれぞれ1回だけ行う。
- invalid / expired refresh token が `reauth_required` になる。
- refresh endpoint の timeout / 5xx が cache を壊さず `auth_unavailable` になる。
- code exchange で `public_repo` または refresh token が欠けた場合は cache を作らない。
- OAuth callback の state 不一致では exchange と cache write を行わない。
- cache file の mode が `0600`、更新が atomic である。
- error message や test log に秘密値が含まれない。

### 12.3 実行コマンド

```bash
uv run pytest week2/tests -q
uv run ruff check week2
```

## 13. 手動 E2E と提出証拠

### 13.1 成功シナリオ

専用 repo に、本文のある open Issue を2件以上用意する。Claude Code で次の実 prompt を使う。

> 設定済みリポジトリで最近更新された open Issue を探し、1件の内容を読んで、次の行動を
> 要約した短いコメント案を作ってください。まずプレビューを示し、私の承認を待ってから
> 投稿してください。

期待する実行列:

1. `list_issues(state="open", sort="updated", direction="desc", limit=5)`
2. `get_issue(issue_number=<一覧で得た番号>)`
3. `add_issue_comment(issue_number=<同じ番号>, body=<案>, dry_run=true)`
4. 利用者がプレビューを確認して投稿を承認
5. 同じ番号・本文で `add_issue_comment(..., dry_run=false)`

write-up には実測した prompt、tool 名、引数、整形済み結果、最終回答、作成された GitHub
comment URL を記録する。token や Authorization header を記録せず、想定ログを実績として
書かない。

### 13.2 失敗と回復シナリオ

存在しない正の番号 `999999` を `get_issue` に渡して実 API の 404 を起こす。

期待する挙動:

1. tool が `not_found`、`retryable=false`、`action="Call list_issues ..."` を返す。
2. agent は同じ call を繰り返さない。
3. agent が `list_issues` に戻り、有効な `issue_number` を選ぶ。

この一連を write-up に残す。schema validation だけではなく、外部 API failure を構造化エラーで
回復できた証拠にする。

### 13.3 token が実行中に失効する場合

自動試験では 401 → refresh、invalid refresh token → `reauth_required` を再現する。別の試験で
refresh endpoint の一時障害が `auth_unavailable` になることも確認する。手動確認では cache の
refresh token を失効させ、tool call がブラウザーを開かず auth command を返すことを確認する。
認証をやり直した後は MCP server を再起動し、読み取りを再実行する。

## 14. 実装順序

1. **足場**: dependency、ignore、package、README、example config を追加する。
2. **GitHub client**: 設定検証、cache、OAuth auth command、refresh、REST/error mapping を作る。
3. **MCP contract**: response model、instructions、3 tools、annotations、serve command を作る。
4. **自動試験**: MockTransport unit test と stdio protocol test を通す。
5. **実統合**: OAuth App と sandbox repo を作成し、Claude Code へ登録する。
6. **観察と調整**: agent の誤用を1回観察し、schema/docstring/instructions のいずれかを改善する。
7. **提出物**: 実測 transcript、failure recovery、根拠、行番号を `writeup.md` に記入する。

agent の観察前に「変更したこと」を創作しない。実際の誤用がなければ、意図的に曖昧な prompt
で動作を観察してから、確認できた事実に基づき改善する。

## 15. 課題要件との対応表

| 課題要件 | 設計上の対応 | 完了時の証拠 |
|---|---|---|
| FastMCP / stdio | `github_mcp.py serve` | README の単一コマンド、protocol test |
| 3つ以上の tool | list / get / add comment の3つ | `tools/list` の assertion |
| tool が compose | `issue_number` を同名・同型で受け渡す | 成功 transcript |
| 実状態を変える tool | `add_issue_comment(dry_run=false)` | GitHub comment URL |
| schema-level constraint | Literal、Field の範囲・長さ | JSON Schema assertion、validation test |
| shaped output | Pydantic response と field 選別 | unit test、write-up |
| actionable structured errors | code / retryable / action | 404 failure transcript、unit test |
| chaining docstring | ID の出所と呼出順を各 tool に記載 | `tools/list` description assertion |
| cross-tool instructions | `FastMCP(instructions=...)` | initialize / server inspection |
| annotations | read-only / destructive / idempotent / open-world | protocol test |
| write brake | `dry_run=true` が既定、明示承認後だけ false | protocol test、成功 transcript |
| authorization-code exchange | state + PKCE + local callback + token exchange | auth 実行記録 |
| cached token | repo 外 0600、atomic write | unit test、説明 |
| silent refresh | 60秒前 refresh、token pair rotation | MockTransport test |
| minimal scopes | `public_repo` のみ。refresh は App の expiration 設定で有効化 | consent 画面、write-up の根拠 |
| secrets を commit しない | env、ignored real config、external cache | git 検査 |
| token dies mid-session | refresh 1回、失敗時 reauth、browser なし | unit / manual test |
| client integration | `.mcp.json.example` | committed example |
| E2E chain | list → get → preview → approved write | 実 transcript |
| failure recovery | 404 → list へ戻る | 実 transcript |
| MCP protocol test | stdio subprocess の list / call | pytest result |
| `week2/` の deliverables | source、tests、config、README、write-up | tree と commit |

## 16. 完了判定

実装完了は、次をすべて満たした状態とする。

- `uv run pytest week2/tests -q` と `uv run ruff check week2` が成功する。
- protocol test が stdio subprocess を介して3 tool を確認する。
- 実 OAuth code flow、cache、silent refresh、失効後の再認証案内を確認できる。
- agent が list → get → preview → 利用者承認 → write を実行し、実 comment URL が残る。
- 失敗シナリオで agent が retryability と action に従って回復する。
- `.mcp.json.example` は commit 済みで、実 `.mcp.json`、token cache、Client Secret は未追跡である。
- `writeup.md` のすべての欄が実測値と `file:line` で埋まっている。
- assignment の指定 collaborator と push / Gradescope は、コード完成後の提出手順として実施する。

## 17. 公式資料

- [FastMCP: Tools](https://gofastmcp.com/servers/tools)
- [FastMCP: Server](https://gofastmcp.com/servers/server)
- [FastMCP: Testing](https://gofastmcp.com/servers/testing)
- [MCP Reference Servers: Filesystem](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem)
- [GitHub: Authorizing OAuth apps](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps)
- [GitHub: Scopes for OAuth apps](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps)
- [GitHub REST API: Issues](https://docs.github.com/en/rest/issues/issues)
- [GitHub REST API: Issue comments](https://docs.github.com/en/rest/issues/comments)
- [Claude Code: Connect to tools via MCP](https://code.claude.com/docs/en/mcp)
- [uv CLI: `--directory`](https://docs.astral.sh/uv/reference/cli/)

本書で実装方針は確定している。実装時に変更が必要になった場合は、コードと docstring だけを
先に変えず、本書の該当判断・テスト・課題対応表も同時に更新する。
