# AI活用型 業務自動化ツール集

Python × Claude/OpenAI APIを使った業務効率化ツールのポートフォリオです。
プロンプト設計からPython実装まで一貫して対応できます。

## できること
- 生成AIを使ったテキスト分析（要約・感情分析・キーワード抽出）
- CSV等の大量データに対する一括AI処理バッチツール
- 社内ドキュメント・FAQに基づいて回答するRAGチャットボット構築

## 使用技術
- Python
- Anthropic API (Claude) / OpenAI API
- LlamaIndex（RAG構築）
- Chroma（ベクトルDB）

## プロジェクト一覧

### 1. [text_analyzer](./text_analyzer) — テキスト分析ツール
1件のテキストを要約・感情分析・キーワード抽出し、JSON形式で出力。
リトライ処理・エラーハンドリング実装済み。

### 2. [batch_analyzer](./batch_analyzer) — CSV一括分析ツール
CSVで複数件のテキストを読み込み、一括でAI分析。結果をCSV/JSONで出力。
1件のエラーで全体が止まらない設計。

### 3. [rag_chatbot](./rag_chatbot) — RAGチャットボット
社内文書・FAQをもとに質問に回答するチャットボット。
Chromaでベクトルを永続化し、2回目以降は高速起動。

## お問い合わせ
実務での業務自動化・生成AI導入のご相談はお気軽にどうぞ。