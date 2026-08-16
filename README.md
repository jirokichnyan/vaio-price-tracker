# VAIO VJPJ21 価格トラッカー

楽天市場に出品されている中古 VAIO VJPJ21シリーズを毎日自動収集し、
中古ランク（美品/傷ありなど）とスペック（メモリ/SSD容量）ごとに
価格推移をダッシュボードで確認できるようにする仕組みです。

```
collector.py          楽天APIを叩いてCSVに1日分追記するスクリプト
.github/workflows/    GitHub Actionsで毎日自動実行する設定
docs/index.html       価格推移ダッシュボード（GitHub Pagesで公開）
docs/data/price_history.csv  蓄積される価格履歴データ
```

## セットアップ手順

### 1. 楽天ウェブサービスのAPIキーを取得

1. https://webservice.rakuten.co.jp/ にログイン（楽天会員でOK）
2. 「アプリID発行」からアプリケーションを登録
3. `applicationId`（アプリID）と `accessKey`（アクセスキー）を取得
   - 2026-07-01版APIから `accessKey` も必須になっています

### 2. このプロジェクトをGitHubリポジトリにする

1. 新しいリポジトリを作成し、このフォルダ一式をpush
2. リポジトリの Settings → Secrets and variables → Actions で以下を登録
   - `RAKUTEN_APPLICATION_ID`
   - `RAKUTEN_ACCESS_KEY`
   - `RAKUTEN_AFFILIATE_ID`（任意、アフィリエイトIDがあれば）

### 3. GitHub Pagesを有効化

Settings → Pages → Source を `Deploy from a branch` → ブランチ `main` / フォルダ `/docs` に設定。
数分後に `https://<ユーザー名>.github.io/<リポジトリ名>/` でダッシュボードが常時閲覧できます。

### 4. 動作確認

Actions タブから `VAIO Price Tracker` ワークフローを手動実行（workflow_dispatch）して、
`docs/data/price_history.csv` にデータが追記されるか確認してください。
以降は毎日 07:00 JST に自動実行されます。

## 分類ロジックについて（重要な制約）

楽天市場商品検索APIには「中古/新品」や「ランク」を示す専用フィールドが存在しません。
そのため `collector.py` は商品名・キャッチコピー・商品説明のテキストを正規表現で走査し、
「美品」「傷あり」「ジャンク」等のキーワードからランクを推定しています（`RANK_PATTERNS`）。
メモリ・SSD容量も同様にテキストからの推定です。

出品者によって表記揺れがあるため、完全な精度は保証できません。
実際に検知した商品を確認しながら、`collector.py` の正規表現パターンを
ご自身の観測範囲に合わせて調整していくことをおすすめします
（例: 見慣れない書き方をする出品者が増えたら `RANK_PATTERNS` にパターンを追加）。

## 収集頻度・保存先を変えたい場合

- 頻度: `.github/workflows/track.yml` の `cron` を変更（例: 1日3回なら `0 0,8,16 * * *`）
- 保存先: `collector.py` の `OUTPUT_CSV` を変更。過去データを消さない限りCSVは追記され続けます
