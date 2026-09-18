import sqlite3
from pathlib import Path

from generate_demo_source import DEMO_FACTS, generate_demo_source


def fake_hermes(repo: Path) -> None:
    pkg = repo / "plugins" / "memory" / "holographic"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "hermes_lazy_helper.py").write_text("MARKER = 'loaded-lazily'\n")
    pkg.mkdir(parents=True)
    for init in [
        repo / "plugins" / "__init__.py",
        repo / "plugins" / "memory" / "__init__.py",
        pkg / "__init__.py",
    ]:
        init.write_text("")
    (pkg / "store.py").write_text(
        """import sqlite3\n"""
        """class MemoryStore:\n"""
        """    def __init__(self, db_path, default_trust=0.5):\n"""
        """        from hermes_lazy_helper import MARKER\n"""
        """        assert MARKER == \"loaded-lazily\"\n"""
        """        self.db_path = str(db_path); self.conn=sqlite3.connect(self.db_path)\n"""
        """        self.conn.executescript("CREATE TABLE facts (fact_id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT UNIQUE, category TEXT, tags TEXT, trust_score REAL, retrieval_count INTEGER DEFAULT 0, helpful_count INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, hrr_vector BLOB); CREATE TABLE entities (entity_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, entity_type TEXT DEFAULT 'unknown', aliases TEXT DEFAULT '', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP); CREATE TABLE fact_entities (fact_id INTEGER, entity_id INTEGER, PRIMARY KEY(fact_id,entity_id)); CREATE TABLE memory_banks (bank_id INTEGER PRIMARY KEY, bank_name TEXT, vector BLOB, dim INTEGER, fact_count INTEGER, updated_at TIMESTAMP);")\n"""
        """        self.conn.commit(); self.default_trust=default_trust\n"""
        """    def add_fact(self, content, category="general", tags=""):\n"""
        """        cur=self.conn.execute("INSERT INTO facts(content,category,tags,trust_score) VALUES(?,?,?,?)",(content,category,tags,self.default_trust)); self.conn.commit(); return cur.lastrowid\n"""
        """    def record_feedback(self, fact_id, helpful):\n"""
        """        delta=.05 if helpful else -.10; inc=1 if helpful else 0; self.conn.execute("UPDATE facts SET trust_score=MIN(1,MAX(0,trust_score+?)), helpful_count=helpful_count+?, updated_at=CURRENT_TIMESTAMP WHERE fact_id=?",(delta,inc,fact_id)); self.conn.commit(); return {}\n"""
        """    def update_fact(self, fact_id, content=None, tags=None, **kwargs):\n"""
        """        if content is not None: self.conn.execute("UPDATE facts SET content=?, updated_at=CURRENT_TIMESTAMP WHERE fact_id=?",(content,fact_id))\n"""
        """        if tags is not None: self.conn.execute("UPDATE facts SET tags=?, updated_at=CURRENT_TIMESTAMP WHERE fact_id=?",(tags,fact_id))\n"""
        """        self.conn.commit(); return True\n"""
        """    def search_facts(self, query, min_trust=0.0, limit=5):\n"""
        """        row=self.conn.execute("SELECT fact_id FROM facts ORDER BY fact_id LIMIT 1").fetchone();\n"""
        """        if row: self.conn.execute("UPDATE facts SET retrieval_count=retrieval_count+1 WHERE fact_id=?",(row[0],)); self.conn.commit()\n"""
        """        return []\n"""
        """    def list_facts(self, min_trust=0.0, limit=1000):\n"""
        """        return [dict(zip(["fact_id","content"],r)) for r in self.conn.execute("SELECT fact_id,content FROM facts LIMIT ?",(limit,))]\n"""
        """    def close(self): self.conn.close()\n"""
    )


def test_generator_uses_hermes_public_operations(tmp_path: Path):
    repo = tmp_path / "hermes"
    fake_hermes(repo)
    db = tmp_path / "memory_store.db"
    report = generate_demo_source(repo, db)
    assert report["source_tool"] == "Hermes Holographic MemoryStore"
    assert report["source_operations"]["add_fact"] == len(DEMO_FACTS) == 72
    assert report["source_operations"]["record_feedback"] == 10
    assert report["source_operations"]["update_fact"] == 1
    assert report["source_operations"]["search_facts"] == 8
    assert report["fact_count"] == 72
    assert report["stored_fact_count"] == 72
    assert report["sqlite_integrity_check"] == "ok"
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 72
        atlas = conn.execute(
            "SELECT content FROM facts WHERE content LIKE 'Project Atlas uses a three-stage%'"
        ).fetchone()
        assert atlas is not None and "portability evidence" in atlas[0]
    finally:
        conn.close()
