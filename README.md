# 日本株テクニカルシグナル通知システム

日本株のウォッチリストを毎日自動でチェックし、テクニカル指標（ゴールデンクロス/デッドクロス・RSI・MACD）に基づく売買シグナルをLINEに通知し、あわせて現状をまとめたダッシュボードをWebページとして公開する仕組みです。GitHub Actionsで無料・無人稼働します。

**投資助言ではありません。** 一般的なテクニカル指標を機械的に組み合わせただけの参考情報であり、将来の値動きを保証するものではありません。投資判断は必ずご自身の責任で行ってください。

---

## ファイル構成

```
stock-signal-system/
├── analyze.py              # メイン実行スクリプト
├── indicators.py           # SMA/RSI/MACDの計算
├── signals.py              # 売買シグナル判定ロジック
├── notify.py                # LINE Messaging APIへの通知送信
├── dashboard.py             # HTMLダッシュボード生成
├── watchlist.py             # 監視銘柄リスト（編集はここだけでOK）
├── holdings.py               # 保有銘柄リスト（Issueフォームからも編集可能）
├── nikkei225.py              # 買い時ランキングの対象ユニバース（日経225）
├── ranking.py                # 買い時ランキングのロジック
├── test_logic.py             # シグナル判定ロジックの単体テスト（ネット接続不要）
├── test_ranking_logic.py      # ランキングロジックの単体テスト（ネット接続不要）
├── requirements.txt
├── .github/workflows/stock-check.yml         # 自動実行の設定
├── .github/workflows/handle-registration.yml # Issueフォームからの登録処理
├── .github/ISSUE_TEMPLATE/                    # 保有銘柄登録などのIssueフォーム
└── docs/index.html           # 生成されるダッシュボード(GitHub Pagesで公開)
```

## セットアップ手順

### 1. GitHubアカウントを作成

https://github.com/signup にアクセスし、メールアドレスで無料アカウントを作成します。

### 2. リポジトリを作成

1. 右上の「+」→「New repository」
2. Repository name: 例 `stock-signal-system`
3. 「Public」または「Private」どちらでも可（Privateの場合もこの用途なら無料枠で十分です）
4. 「Create repository」

### 3. ファイルをアップロード

作成したリポジトリのページで「uploading an existing file」（またはリポジトリ内の「Add file」→「Upload files」）を選び、このフォルダの中身をすべてドラッグ&ドロップしてアップロードします。フォルダ構造（`.github/workflows/` 以下も含む）を保ったままアップロードしてください。うまくいかない場合は、GitHub Desktopアプリを使う方法もあります。

### 4. LINE公式アカウント・Messaging APIの準備

LINE Notifyは2025年3月末で終了しているため、後継のLINE Messaging APIを使います。

1. https://www.linebiz.com/jp/entry/ からLINE公式アカウントを作成（無料）
2. [LINE Developersコンソール](https://developers.line.biz/console/) にログインし、作成した公式アカウントに対応するプロバイダー・チャネル（Messaging API）を開く
3. 「Messaging API設定」タブで「チャネルアクセストークン（長期）」を発行し、値をコピーしておく
4. スマホのLINEアプリで、作成した公式アカウントを友だち追加しておく（QRコードはLINE Developersコンソールまたは公式アカウントマネージャーで確認できます）

※ 通知は「broadcast」（友だち全員に配信）方式にしているため、自分だけが友だち登録していれば実質的に自分専用の通知になります。他の人にも読まれたくない場合、他の人を友だち追加しないよう注意してください。

### 5. GitHubにLINEのトークンを登録

1. リポジトリの「Settings」→「Secrets and variables」→「Actions」
2. 「New repository secret」
3. Name: `LINE_CHANNEL_ACCESS_TOKEN`
4. Secret: 手順4でコピーしたトークンを貼り付けて保存

### 6. GitHub Pagesを有効化（ダッシュボード公開用）

1. リポジトリの「Settings」→「Pages」
2. 「Source」を「Deploy from a branch」、Branch を `main` / フォルダを `/docs` に設定して保存
3. 数分後に `https://(あなたのユーザー名).github.io/(リポジトリ名)/` でダッシュボードが見られるようになります（初回の自動実行後に反映されます）

### 7. 動作確認

1. リポジトリの「Actions」タブを開く
2. 左側の「日本株テクニカルシグナルチェック」を選択
3. 右側の「Run workflow」ボタンで手動実行
4. 数十秒〜1分程度で完了し、シグナルがあればLINEに通知が届き、`docs/index.html` が更新されます

以降は `.github/workflows/stock-check.yml` に設定したスケジュール（平日 朝8:00・後場終了後15:40、日本時間）で自動的に実行されます。

## 監視銘柄のカスタマイズ

`watchlist.py` を編集して銘柄コードと名称を追加・削除してください。証券コードの後ろに `.T` を付けた形式です（例: トヨタ自動車なら `7203.T`）。

## 保有銘柄の登録・買い時ランキングの設定（Issueフォームから操作可能）

コードを直接編集しなくても、GitHubの「Issues」タブからフォームで登録・変更ができます。

1. リポジトリの「Issues」タブ →「New issue」
2. 用意されているテンプレートから選択
   - **① 保有銘柄を追加**: 証券コードと銘柄名を入力すると、`holdings.py` に自動追加されます
   - **② 保有銘柄を削除**: 証券コードを入力すると、`holdings.py` から自動削除されます
   - **③ 買い時ランキングの価格上限を変更**: 金額を入力すると、`analyze.py` の`RANKING_PRICE_CEILING`が自動更新されます
3. 「Submit new issue」を押すと、数十秒後に自動でファイルが更新され、Issueにコメントが付いて自動的にクローズされます（`.github/workflows/handle-registration.yml` が処理しています）

保有銘柄として登録された銘柄は、ウォッチリストとは別に「保有銘柄」セクションとしてダッシュボードに表示され、シグナル（買い/売り）が出るとLINE通知にも `[保有]` として含まれます（LINE通知を設定している場合）。

もちろん、`holdings.py` や `analyze.py` を直接編集する方法でも問題ありません。

## 買い時ランキングについて

日経225の構成銘柄（`nikkei225.py`）の中から、株価が指定した上限（デフォルト1500円）以下の銘柄を対象に、シグナル判定ロジックによる「買いの根拠の強さ」でランキングを作成し、ダッシュボードに上位20件を表示します。日経225の構成銘柄は入れ替えがあるため、`nikkei225.py` は定期的な見直しが必要です。

## シグナル判定ロジックについて

以下の3系統を組み合わせています。複数が同時に成立するほど「強いシグナル」として扱われます。

- **移動平均クロス**: 5日線が25日線を上抜け（ゴールデンクロス＝買い）／下抜け（デッドクロス＝売り）
- **RSI(14)**: 30を上抜けたら売られすぎからの反発（買い）、70を下抜けたら買われすぎからの反落（売り）。RSIが70以上/30以下の水準自体も過熱警戒として計上
- **MACD**: MACD線がシグナル線を上抜け（買い）／下抜け（売り）

ロジックは `signals.py` にまとまっているので、条件の追加・調整も可能です。

## ロジックの単体テスト

ネットワーク接続なしで、合成データを使ってロジックの正しさを検証できます。

```
pip install -r requirements.txt
python test_logic.py
```

## 注意事項

- yfinance は無料の非公式データソースのため、まれに一時的な取得エラーが起きることがあります（`analyze.py` は1銘柄が失敗しても他銘柄の処理を継続します）
- 実際の自動発注（売買の自動執行）は行いません。あくまでシグナルの通知とダッシュボード表示のみです
- 本システムの利用によって生じたいかなる損失についても責任を負いかねます
