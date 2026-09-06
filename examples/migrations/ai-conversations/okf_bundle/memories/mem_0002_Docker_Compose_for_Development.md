# Docker Compose for Development

**Type:** auto-classified
**Source:** chatgpt
**Confidence:** 0.8
**Tags:** chatgpt, ai-conversation
**Created:** 2023-11-17 05:46:40+00:00

---

[User message 1]: How do I set up Docker Compose for a full-stack app with React, FastAPI, and PostgreSQL?

[Assistant message 2]: Here's a docker-compose.yml:

```yaml
version: '3.8'
services:
  frontend:
    build: ./frontend
    ports: ['3000:3000']
    volumes: ['./frontend/src:/app/src']
    depends_on: [backend]

  backend:
    build: ./backend
    ports: ['8000:8000']
    environment:
      - DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/mydb
    volumes: ['./backend/app:/app/app']
    depends_on: [db]

  db:
    image: postgres:16
    environment:
      POSTGRES_DB: mydb
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes: ['pgdata:/var/lib/postgresql/data']
    ports: ['5432:5432']

volumes:
  pgdata:
```

[User message 3]: How do I add hot-reloading for the backend?

[Assistant message 4]: Use uvicorn with `--reload`:

```yaml
backend:
  command: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
  volumes:
    - ./backend/app:/app/app
```

The volume mount + `--reload` flag gives you hot-reloading.

---
*Migration metadata:*
**Source:** chatgpt:conversation
**ChatGPT title:** Docker Compose for Development
**Message count:** 4
**Source created_at:** 2023-11-17T05:46:40+00:00
