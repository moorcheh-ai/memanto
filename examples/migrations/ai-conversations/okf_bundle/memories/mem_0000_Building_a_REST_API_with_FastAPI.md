# Building a REST API with FastAPI

**Type:** auto-classified
**Source:** chatgpt
**Confidence:** 0.8
**Tags:** chatgpt, ai-conversation
**Created:** 2023-11-14 22:13:20+00:00

---

[User message 1]: I want to build a REST API with FastAPI for a todo app. What's the best project structure?

[Assistant message 2]: Here's a recommended project structure for a FastAPI todo app:

```
project/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── models.py
│   ├── schemas.py
│   ├── database.py
│   └── routers/
│       ├── __init__.py
│       └── todos.py
├── tests/
└── requirements.txt
```

[User message 3]: How do I set up SQLAlchemy with async support in this structure?

[Assistant message 4]: For async SQLAlchemy, use `AsyncSession` with `create_async_engine`:

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

engine = create_async_engine('postgresql+asyncpg://${DB_USER}:${DB_PASS}@${DB_HOST}/${DB_NAME}')
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession)
```

[User message 5]: What about dependency injection for the database session?

[Assistant message 6]: Use FastAPI's dependency injection:

```python
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

@app.get('/todos')
async def get_todos(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Todo))
    return result.scalars().all()
```

---
*Migration metadata:*
**Source:** chatgpt:conversation
**ChatGPT title:** Building a REST API with FastAPI
**Message count:** 6
**Source created_at:** 2023-11-14T22:13:20+00:00
