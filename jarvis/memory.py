"""Conversation memory: every turn is persisted; the prompt gets a sliding window of recent turns."""
from .storage import Store, now_iso


class ConversationMemory:
    def __init__(self, store: Store, session: str = "default", window: int = 12):
        self.store, self.session, self.window = store, session, window

    def add(self, role: str, content: str) -> None:
        self.store.execute("INSERT INTO messages(session, role, content, ts) VALUES (?, ?, ?, ?)",
                           (self.session, role, content, now_iso()))

    def recent(self) -> list[dict]:
        rows = self.store.query(
            "SELECT role, content FROM messages WHERE session = ? ORDER BY id DESC LIMIT ?",
            (self.session, self.window))
        return rows[::-1]

    def clear(self) -> None:
        self.store.execute("DELETE FROM messages WHERE session = ?", (self.session,))
