課題

レビューやアンケートの自由記述など、数十〜数百件単位のテキストデータを1件ずつAIに投げて分析するのは非効率。かつ、途中でAPIエラーが1件でも起きると処理全体が止まってしまうと業務利用に耐えない。

実装内容

CSVファイル（1列がテキストデータ）を読み込み、各行に対して要約・感情分析・キーワード抽出を実行し、結果をCSVまたはJSONにまとめて出力するバッチツール。text_analyzer の分析ロジックをベースに、複数件処理向けに拡張。

分析対象の列名は -c オプションで指定可能（デフォルトは text）
出力形式は拡張子で自動判定（.csv / .json）
1件のAPIエラーで全体が止まらないよう、失敗した行は error 情報付きで結果に残して処理を継続
実行例
bash
python batch_analyzer.py reviews.csv -o result.csv

入力（reviews.csv）：

id,text
1,配送はとても早かったが、商品の品質はイマイチだった。
2,期待以上の商品でした。また利用したいです。
3,普通の商品でした。特に不満はありません。

出力（result.csv）：id・text列に加えて summary / sentiment / keywords 列が追加された状態で出力される。

使用技術
Python
Anthropic API（Claude）
工夫した点
1件ずつの処理結果を逐次ログ出力（処理中 2/3 ...）し、大量データ処理時も進捗が見える設計
APIのレート制限を避けるため、各リクエスト間に待機時間（time.sleep(0.5)）を挿入
keywords（リスト型）をCSV出力時はカンマ区切りの文字列に変換するなど、CSV/JSON双方の出力形式に対応
失敗した行も結果に残すことで「一部失敗してもいいから全件処理してほしい」という実務ニーズに対応
セットアップ
bash
pip install -r requirements.txt

.env に以下を設定：

ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxx