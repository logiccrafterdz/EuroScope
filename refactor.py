import re

filepath = r"c:\Users\Hp\Desktop\EuroScope\euroscope\data\storage.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update init method
content = content.replace(
    "self._db: Optional[aiosqlite.Connection] = None",
    "self._pool = None\n        self._pool_size = 5"
)

# 2. Update __init__ imports
if "from contextlib import asynccontextmanager" not in content:
    content = content.replace("from typing import Any, Optional", "from typing import Any, Optional\nimport asyncio\nfrom contextlib import asynccontextmanager")

# 3. Replace _get_db and close implementation
new_get_db = """    async def _get_pool(self) -> asyncio.Queue:
        if self._pool is None:
            self._pool = asyncio.Queue(maxsize=self._pool_size)
            for _ in range(self._pool_size):
                conn = await aiosqlite.connect(str(self.db_path), timeout=30.0)
                conn.row_factory = aiosqlite.Row
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                await conn.execute("PRAGMA busy_timeout=30000")
                await self._pool.put(conn)
        return self._pool

    @asynccontextmanager
    async def _get_db(self):
        \"\"\"Acquire a database connection from the pool.\"\"\"
        pool = await self._get_pool()
        conn = await pool.get()
        try:
            yield conn
        finally:
            pool.put_nowait(conn)

    async def close(self):
        \"\"\"Close all async database connections in the pool.\"\"\"
        if self._pool is not None:
            while not self._pool.empty():
                conn = await self._pool.get()
                await conn.close()
            self._pool = None"""

# Use regex to find old _get_db to close
old_get_db_regex = re.compile(r"    async def _get_db.*?self\._db = None", re.DOTALL)
content = old_get_db_regex.sub(new_get_db, content)

class StorageRefactorer:
    def process_file(self, content):
        lines = content.splitlines(keepends=True)
        new_lines = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if "db = await self._get_db()" in line:
                indent = len(line) - len(line.lstrip())
                new_lines.append(" " * indent + "async with self._get_db() as db:\n")
                
                i += 1
                while i < len(lines):
                    next_line = lines[i]
                    stripped = next_line.strip()
                    if stripped:
                        next_indent = len(next_line) - len(next_line.lstrip())
                        # Break if we hit a def/class at the outer level
                        if next_indent < indent and not stripped.startswith(')') and not stripped.startswith(']'):
                            # Only break if it's a completely new construct, not a stray closing bracket.
                            break
                    # Indent the line by 4 spaces
                    new_lines.append(" " * 4 + next_line if stripped else next_line)
                    i += 1
                continue
            new_lines.append(line)
            i += 1
        return "".join(new_lines)

final_content = StorageRefactorer().process_file(content)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(final_content)

print("Storage refactored locally.")
