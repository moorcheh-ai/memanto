--- a/memanto/app/config.py
+++ b/memanto/app/config.py
@@ -15,6 +15,7 @@
 
 class Settings:
     def __init__(self):
         self.OKF_EXPORT_DIR = './okf_exports'
         self.MEMANTO_MIGRATE_INSupported_tools = ['Mem0', 'Letta', 'Supermemory']
+        self.MEMANTO_MIGRATE_OUT_SUPPORTED_TOOLS = ['OKF']
 
--- a/memanto/cli/migrate.py
+++ b/memanto/cli/migrate.py
@@ -50,6 +50,14 @@
     async def _migrate_from_tool(self, tool_name: str):
         # existing implementation...
         pass
 
+    async def _migrate_to_okf(self, okf_dir: str):
+        # implement OKF export logic here
+        pass
+
+    async def migrate_to_okf(self, okf_dir: str):
+        await self._migrate_to_okf(okf_dir)
+
--- a/memanto/app/routes/migrate.py
+++ b/memanto/app/routes/migrate.py
@@ -20,6 +20,10 @@
     @app.post("/migrate/{tool_name}")
     async def migrate_from_tool(tool_name: str):
         # existing implementation...
         pass
 
+    @app.post("/migrate/okf/{okf_dir}")
+    async def migrate_to_okf(okf_dir: str):
+        # call migrate_to_okf logic here
+        pass
