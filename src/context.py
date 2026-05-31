class ContextManager:
    def __init__(self):
        self._contexts = {}
    def create(self, ctx_id):
        self._contexts[ctx_id] = {"messages": [], "tokens": 0}
    def cleanup(self, ctx_id):
        self._contexts.pop(ctx_id, None)
    def cleanup_all(self):
        self._contexts.clear()