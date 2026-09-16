課題

社内マニュアルやFAQをAIチャットボットに読み込ませ、その内容に基づいて回答させたい。しかし、ドキュメント量が多い場合に全文をプロンプトに詰め込むのは非効率で、コストも高くなる。

実装内容

RAG（Retrieval-Augmented Generation）構成のQAチャットボット。ドキュメントをベクトル化してインデックスを構築し、質問内容に関連する部分だけを検索してAIに渡すことで、正確かつ低コストな回答を実現する。

文書の埋め込み（Embedding）：OpenAI API（text-embedding-3-small）
回答生成：Anthropic API（Claude）
ベクトルDB：Chroma（ローカルにディスク永続化）

初回起動時のみドキュメントを読み込んでインデックスを構築し、2回目以降は保存済みインデックスを読み込むことで起動時間とEmbeddingコストを削減している。

実行例
bash
python rag_chatbot.py
[info] 既存のインデックスを読み込みます（再構築なし）
[info] 準備完了。質問を入力してください（終了は exit、再構築は rebuild）

質問: 返品はできますか？
回答: 商品到着後14日以内であれば、未使用品に限り返品可能です。返送料はお客様負担となります。

ドキュメントを更新した場合は rebuild と入力するとインデックスを削除し、次回起動時に再構築される。

使用技術
Python
Anthropic API（Claude）／OpenAI API（Embedding）
LlamaIndex（ドキュメント読み込み・インデックス構築）
Chroma（ベクトルDBの永続化）
工夫した点
chromadb.PersistentClient でインデックスをディスクに保存し、既存インデックスがあれば再構築をスキップする設計にすることで、Embedding APIの呼び出しコストと起動時間を削減
rebuild コマンドを用意し、ドキュメント更新時に簡単にインデックスを作り直せるようにした
LLM（Claude）とEmbeddingモデル（OpenAI）を別プロバイダで組み合わせ、それぞれの強みを活用する構成にした
セットアップ
bash
pip install -r requirements.txt

docs/ フォルダに読み込ませたいテキストファイルを配置。

.env に以下を設定：

ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxx
OPENAI_API_KEY=sk-xxxxxxxxxxxx