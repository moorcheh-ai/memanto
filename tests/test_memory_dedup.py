import pytest
from memanto.core.memory import MemoryManager
from memanto.core.retrieval import retrieve_relevant


def test_retrieval_deduplication():
    manager = MemoryManager(store=InMemoryStore())
    query = "How to deploy memanto?"
    content_dup = "部署步骤如下：先安装依赖"
    manager.add_memory("u1", content_dup, {})
    manager.add_memory("u1", content_dup, {})   # 重复写入
    results = retrieve_relevant(query, manager.store, top_k=2)
    contents = [r["content"] for r in results]
    assert len(contents) == len(set(contents)), "返回内容中存在重复"
