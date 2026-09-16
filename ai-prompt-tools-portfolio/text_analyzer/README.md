課題

問い合わせ内容やレビューなどのテキストデータを、人手で1件ずつ読んで「要約する」「感情を判定する」「要点を拾う」のは時間がかかり、担当者によって評価にばらつきが出やすい。

実装内容

Claude APIに対して「必ず指定のJSON形式のみで出力する」というプロンプトを与え、テキストを渡すだけで以下を自動生成するCLIツール。

summary：2〜3文程度の要約
sentiment：positive / negative / neutral の3分類
keywords：要点となるキーワード（3つ程度）

入力はテキストの直接指定、またはテキストファイルのパス指定のどちらにも対応。

実行例
bash
python text_analyzer.py "このサービスは配送が早くて満足だが、サポート対応が遅いのが残念だった。"

出力：

json
{
  "summary": "配送は早いが、サポート対応の遅さに不満がある。",
  "sentiment": "negative",
  "keywords": ["配送", "サポート対応", "不満"]
}
使用技術
Python
Anthropic API（Claude）
工夫した点
レート制限（RateLimitError）や接続エラー（APIConnectionError）発生時に指数バックオフで自動リトライする仕組みを実装
モデルが前置き文などJSON以外の文字列を出力してしまった場合に備え、文字列中の { } 範囲だけを抽出してパースする保険処理を実装
response.usage からトークン使用量を取得し、標準エラー出力に表示（標準出力にはJSON結果のみを流すため、他プログラムへのパイプ処理と両立できる設計）
セットアップ
bash
pip install -r requirements.txt

.env に以下を設定：

ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxx