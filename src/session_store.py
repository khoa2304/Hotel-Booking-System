import secrets
import threading
import time


class SessionStore:
    def __init__(self, lifetime_minutes: int = 60, clock=None):
        self.lifetime_seconds = max(1, lifetime_minutes * 60)
        self.clock = clock or time.time
        self._sessions: dict[str, dict] = {}
        self._lock = threading.RLock()

    def create(self) -> tuple[str, dict]:
        with self._lock:
            session_id = secrets.token_hex(16)
            session = {"_last_seen": self.clock()}
            self._sessions[session_id] = session
            return session_id, session

    def get(self, session_id: str) -> dict | None:
        if not session_id:
            return None
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            now = self.clock()
            if now - session.get("_last_seen", now) > self.lifetime_seconds:
                del self._sessions[session_id]
                return None
            session["_last_seen"] = now
            return session

    def destroy(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)
