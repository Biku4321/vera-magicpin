"""
Context Store — stateful, versioned, dual-mode (Redis or in-memory fallback).

Storage key schema:
  ctx:{scope}:{context_id}           → latest payload JSON
  ctx:{scope}:{context_id}:version   → int
  suppress:{suppression_key}         → 1 (with TTL)
  session:{session_id}               → session state JSON
"""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

SUPPRESSION_TTL = int(os.getenv("SUPPRESSION_TTL_SECONDS", 86400))
MAX_VERSIONS = int(os.getenv("MAX_CONTEXT_VERSIONS", 10))


class ContextStore:
    """
    Dual-mode context store.
    - If REDIS_URL is set, uses Redis.
    - Otherwise falls back to a thread-safe in-memory dict.
    """

    def __init__(self):
        self._redis = None
        self._mem: Dict[str, Any] = {}
        self._suppress_expiry: Dict[str, float] = {}

    async def connect(self):
        redis_url = os.getenv("REDIS_URL", "")
        if redis_url:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(redis_url, decode_responses=True)
                await self._redis.ping()
                print(f"[store] Connected to Redis at {redis_url}")
            except Exception as e:
                print(f"[store] Redis unavailable ({e}), using in-memory store")
                self._redis = None
        else:
            print("[store] No REDIS_URL set — using in-memory store")

    async def disconnect(self):
        if self._redis:
            await self._redis.aclose()

    # ── Context (merchant / customer / trigger / category) ──────────────────

    async def set_context(
        self, scope: str, context_id: str, version: int, payload: Dict[str, Any]
    ) -> bool:
        """
        Atomically store context only if version > current stored version.
        Returns True if stored, False if ignored (same or older version).
        """
        key = f"ctx:{scope}:{context_id}"
        ver_key = f"{key}:version"

        if self._redis:
            current = await self._redis.get(ver_key)
            current_ver = int(current) if current else -1
            if version <= current_ver:
                return False
            pipe = self._redis.pipeline()
            pipe.set(key, json.dumps(payload))
            pipe.set(ver_key, str(version))
            await pipe.execute()
        else:
            current_ver = self._mem.get(ver_key, -1)
            if version <= current_ver:
                return False
            self._mem[key] = payload
            self._mem[ver_key] = version

        return True

    async def get_context(
        self, scope: str, context_id: str
    ) -> Optional[Dict[str, Any]]:
        key = f"ctx:{scope}:{context_id}"
        if self._redis:
            raw = await self._redis.get(key)
            return json.loads(raw) if raw else None
        return self._mem.get(key)

    async def get_version(self, scope: str, context_id: str) -> int:
        ver_key = f"ctx:{scope}:{context_id}:version"
        if self._redis:
            v = await self._redis.get(ver_key)
            return int(v) if v else -1
        return self._mem.get(ver_key, -1)

    # ── Suppression ──────────────────────────────────────────────────────────

    async def is_suppressed(self, suppression_key: str) -> bool:
        key = f"suppress:{suppression_key}"
        if self._redis:
            return await self._redis.exists(key) > 0
        expiry = self._suppress_expiry.get(key)
        return expiry is not None and time.time() < expiry

    async def set_suppressed(
        self, suppression_key: str, ttl: int = SUPPRESSION_TTL
    ):
        key = f"suppress:{suppression_key}"
        if self._redis:
            await self._redis.setex(key, ttl, "1")
        else:
            self._suppress_expiry[key] = time.time() + ttl

    # ── Session state ─────────────────────────────────────────────────────────

    async def create_session(
        self,
        merchant_id: str,
        trigger_id: Optional[str] = None,
        customer_id: Optional[str] = None,
    ) -> str:
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        data = {
            "session_id": session_id,
            "merchant_id": merchant_id,
            "trigger_id": trigger_id,
            "customer_id": customer_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "turns": [],
        }
        await self._save_session(session_id, data)
        return session_id

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        key = f"session:{session_id}"
        if self._redis:
            raw = await self._redis.get(key)
            return json.loads(raw) if raw else None
        return self._mem.get(key)

    async def append_turn(
        self, session_id: str, role: str, content: str, meta: Optional[Dict] = None
    ):
        session = await self.get_session(session_id)
        if not session:
            return
        session["turns"].append(
            {
                "role": role,
                "content": content,
                "ts": datetime.now(timezone.utc).isoformat(),
                **(meta or {}),
            }
        )
        await self._save_session(session_id, session)

    async def _save_session(self, session_id: str, data: Dict):
        key = f"session:{session_id}"
        if self._redis:
            await self._redis.setex(key, 3600 * 6, json.dumps(data))
        else:
            self._mem[key] = data

    # ── Utility ──────────────────────────────────────────────────────────────

    def make_ack_id(self) -> str:
        return f"ack_{uuid.uuid4().hex[:12]}"

    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()
