from langchain_chroma import Chroma
import config_data as config


class VectorStoreService(object):
    def __init__(self, embedding, collection_name=None, persist_directory=None):
        """
        :param embedding: 嵌入模型的传入
        :param collection_name: Chroma collection 名称（默认从 config 读取）
        :param persist_directory: Chroma 持久化目录（默认从 config 读取）
        """
        self.embedding = embedding

        self.vector_store = Chroma(
            collection_name=collection_name or config.collection_name,
            embedding_function=self.embedding,
            persist_directory=persist_directory or config.persist_directory,
            collection_metadata={"hnsw:space": "cosine"},
        )

    def get_retriever(self, k: int = None):
        """返回向量检索器, 方便加入chain"""
        k = k or config.retriever_k
        return self.vector_store.as_retriever(search_kwargs={"k": k})

    def get_retriever_with_score(self, k: int = None, score_threshold: float = None):
        """返回带相关性分数阈值的检索器"""
        k = k or config.retriever_k
        search_kwargs = {"k": k}
        if score_threshold is not None:
            search_kwargs["score_threshold"] = score_threshold
        return self.vector_store.as_retriever(
            search_type="similarity_score_threshold",
            search_kwargs=search_kwargs,
        )


if __name__ == '__main__':
    retriever = VectorStoreService(config.get_embedding_model()).get_retriever()

    res = retriever.invoke("我的体重180斤, 尺码推荐")
    print(res)
