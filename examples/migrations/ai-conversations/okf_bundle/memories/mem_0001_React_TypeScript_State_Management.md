# React TypeScript State Management

**Type:** auto-classified
**Source:** chatgpt
**Confidence:** 0.8
**Tags:** chatgpt, ai-conversation
**Created:** 2023-11-16 02:00:00+00:00

---

[User message 1]: I'm working on a React TypeScript project and trying to decide between Redux Toolkit and Zustand for state management. What do you recommend for a medium-sized app?

[Assistant message 2]: For a medium-sized app, **Zustand** is often the better choice:

- Less boilerplate than Redux Toolkit
- Built-in TypeScript support
- No providers needed
- Simple API with great devtools

Redux Toolkit is better if you need complex middleware, time-travel debugging, or your team already knows Redux.

[User message 3]: Can you show me how to set up Zustand with TypeScript for a todo app?

[Assistant message 4]: ```typescript
import { create } from 'zustand'

type Todo = {
  id: string
  text: string
  completed: boolean
}

type TodoStore = {
  todos: Todo[]
  addTodo: (text: string) => void
  toggleTodo: (id: string) => void
  removeTodo: (id: string) => void
}

export const useTodoStore = create<TodoStore>((set) => ({
  todos: [],
  addTodo: (text) => set((state) => ({
    todos: [...state.todos, { id: crypto.randomUUID(), text, completed: false }]
  })),
  toggleTodo: (id) => set((state) => ({
    todos: state.todos.map((t) => t.id === id ? { ...t, completed: !t.completed } : t)
  })),
  removeTodo: (id) => set((state) => ({
    todos: state.todos.filter((t) => t.id !== id)
  }))
}))
```

---
*Migration metadata:*
**Source:** chatgpt:conversation
**ChatGPT title:** React TypeScript State Management
**Message count:** 4
**Source created_at:** 2023-11-16T02:00:00+00:00
