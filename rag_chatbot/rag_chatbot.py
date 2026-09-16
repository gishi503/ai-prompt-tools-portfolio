import os
from dotenv import load_dotenv
import chromadb
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext, Settings
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.llms.anthropic import Anthropic
from llama_index.embeddings.openai import OpenAIEmbedding

load_dotenv()

Settings.llm = Anthropic(
    model="claude-sonnet-4-5",
    api_key=os.getenv("ANTHROPIC_API_KEY")
)
Settings.embed_model = OpenAIEmbedding(
    model="text-embedding-3-small",
    api_key=os.getenv("OPENAI_API_KEY")
)

CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "company_docs"


def build_or_load_index(docs_dir: str = "docs"):
    chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    chroma_collection = chroma_client.get_or_create_collection(COLLECTION_NAME)
    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)

    if chroma_collection.count() > 0:
        print("[info] 既存のインデックスを読み込みます（再構築なし）")
        index = VectorStoreIndex.from_vector_store(vector_store)
    else:
        print("[info] インデックスが存在しないため新規構築します")
        documents = SimpleDirectoryReader(docs_dir).load_data()
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        index = VectorStoreIndex.from_documents(documents, storage_context=storage_context)

    return index


def main():
    index = build_or_load_index()
    query_engine = index.as_query_engine()

    print("[info] 準備完了。質問を入力してください（終了は exit、再構築は rebuild）")
    while True:
        question = input("\n質問: ")
        if question.strip().lower() == "exit":
            break
        if question.strip().lower() == "rebuild":
            import shutil
            shutil.rmtree(CHROMA_PATH, ignore_errors=True)
            print("[info] インデックスを削除しました。再度起動してください。")
            break
        response = query_engine.query(question)
        print(f"回答: {response}")


if __name__ == "__main__":
    main()