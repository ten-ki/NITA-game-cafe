# Asobiba Game Cafe

木のぬくもりがあるカフェ風 UI で、6つのゲームを遊べる **FastAPI + SQLite** 製の Web アプリです。  
当初の Next.js / PostgreSQL 案ではなく、現在の実装に合わせて Python ベースの MVP として構成されています。

## 収録ゲーム

- オセロ
- 将棋
- UNO
- 五目並べ
- 四目並べ
- 大富豪

## MVP 機能

- ユーザー名 + 4桁 PIN の簡易アカウント登録 / ログイン
- ログイン失敗が続いたときの一時ロックと軽い試行制限
- 相手募集向けの軽量掲示板
- ゲームごとの対戦ルーム作成
- WebSocket ベースのリアルタイム同期
- ゲーム中チャット
- 観戦参加
- PC / スマホ向けのレスポンシブ UI

## 技術構成

- Backend: FastAPI
- Template: Jinja2
- Frontend: 軽量 JavaScript + CSS
- Realtime: FastAPI WebSocket
- Storage: SQLite (`asobiba.sqlite3`、`ASOBIBA_DB_PATH` で変更可能)

## セットアップ

既存の仮想環境を使う場合はそのまま起動できます。新しく環境を作る場合は以下を実行してください。

```powershell
cd C:\Users\tende\OneDrive\デスクトップ\asobiba\NITA-game-cafe
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

任意ですが、本番相当で使う場合は署名用シークレットを設定してください。

```powershell
$env:ASOBIBA_SECRET = "replace-this-with-a-random-secret"
```

SQLite の保存先を変えたい場合は、以下のように設定できます。

```powershell
$env:ASOBIBA_DB_PATH = "C:\path\to\asobiba.sqlite3"
```

## 起動方法

```powershell
cd C:\Users\tende\OneDrive\デスクトップ\asobiba\NITA-game-cafe
.\run.ps1
```

または:

```powershell
.\.venv\Scripts\python -m uvicorn main:app --reload
```

起動後は `http://127.0.0.1:8000` を開いてください。  
SQLite データベースは起動時に初期化され、デフォルトでは `asobiba.sqlite3` が利用されます。

## Render デプロイ

このアプリは Render の **Python Web Service** として動かせます。  
`NITA-game-cafe` をそのまま 1 つの GitHub リポジトリとして push し、そのルートにある `render.yaml` を使う前提です。

### 1. Render で新しい Web Service を作成

- Blueprint を使う場合: `NITA-game-cafe` 直下の `render.yaml` をそのまま利用できます
- 手動作成する場合: 以下の値を設定してください

### 2. 手動設定値

- **Root Directory**: 空欄のままで OK
- **Environment**: `Python`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`

### 3. Environment Variables

- **ASOBIBA_SECRET**: 十分に長いランダム文字列
- **ASOBIBA_DB_PATH**: `/var/data/asobiba.sqlite3`

### 4. Persistent Disk

- **Mount Path**: `/var/data`
- **Recommended DB Path**: `/var/data/asobiba.sqlite3`
- **Recommended Size**: 1 GB 以上

`ASOBIBA_DB_PATH` を persistent disk 配下に向けないと、デプロイや再起動のたびに SQLite ファイルが失われます。

### 5. デプロイ後の補足

- ユーザー情報と募集投稿は SQLite に保存されます
- **ルーム状態・対戦進行・チャット履歴はメモリ保持** のため、Render の再起動・再デプロイで消えます
- SQLite + 単一プロセス前提のため、小規模運用向けです

## 使い方

1. `/register` でユーザー名と 4 桁 PIN を登録
2. トップページでゲームを選び、募集タイトルを入れて部屋を作成
3. 作成した募集はトップの掲示板に表示
4. 同じ部屋 URL に参加するとリアルタイム対戦とチャットが利用可能

## 重要な注意事項

- 永続化されるのは **ユーザー情報と募集投稿** が中心です
- **ルーム状態・対戦進行・チャット履歴はメモリ保持** のため、サーバー再起動で消えます
- SQLite と単一プロセス前提のため、本番の高負荷運用には未対応です
- 認証は 4 桁 PIN の簡易方式で、軽い試行制限と一時ロックを実装済みです
- PIN 再発行やアカウント回復は未実装です
- 自動テスト、CI、監視は未整備です
