"""Per-domain rate limiting and bounded concurrency for polite scraping."""

import asyncio
import threading
import time
from collections import defaultdict
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager

from app.services.scraping.url_utils import extract_domain


class DomainRateLimiter:
    """Enforce per-domain minimum cooldown intervals and bounded global/domain concurrency."""

    def __init__(
        self,
        *,
        default_cooldown_seconds: float = 1.0,
        max_concurrent_per_domain: int = 2,
        max_total_concurrent: int = 5,
        domain_cooldowns: dict[str, float] | None = None,
        clock: Callable[[], float] = time.monotonic,
        async_sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        sync_sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if default_cooldown_seconds < 0:
            raise ValueError("default_cooldown_seconds must be non-negative.")
        if max_concurrent_per_domain < 1:
            raise ValueError("max_concurrent_per_domain must be >= 1.")
        if max_total_concurrent < 1:
            raise ValueError("max_total_concurrent must be >= 1.")

        self.default_cooldown_seconds = float(default_cooldown_seconds)
        self.max_concurrent_per_domain = int(max_concurrent_per_domain)
        self.max_total_concurrent = int(max_total_concurrent)
        self._domain_cooldowns: dict[str, float] = {
            extract_domain(k): float(v) for k, v in (domain_cooldowns or {}).items()
        }
        self._clock = clock
        self._async_sleep = async_sleep
        self._sync_sleep = sync_sleep

        self._global_async_sem = asyncio.Semaphore(self.max_total_concurrent)
        self._domain_async_sems: dict[str, asyncio.Semaphore] = {}
        self._domain_async_locks: dict[str, asyncio.Lock] = {}

        self._global_sync_sem = threading.Semaphore(self.max_total_concurrent)
        self._domain_sync_sems: dict[str, threading.Semaphore] = {}
        self._domain_sync_locks: dict[str, threading.Lock] = {}
        self._state_guard = threading.Lock()

        self._last_request_at: dict[str, float] = {}
        self._active_counts: dict[str, int] = defaultdict(int)

    def set_domain_cooldown(self, domain_or_url: str, cooldown_seconds: float) -> None:
        """Configure a custom cooldown interval for a specific domain."""
        if cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must be non-negative.")
        domain = extract_domain(domain_or_url)
        if domain:
            self._domain_cooldowns[domain] = float(cooldown_seconds)

    def get_cooldown(self, domain_or_url: str) -> float:
        """Return the effective cooldown in seconds for a domain or URL."""
        domain = extract_domain(domain_or_url)
        return self._domain_cooldowns.get(domain, self.default_cooldown_seconds)

    def active_count(self, domain_or_url: str) -> int:
        """Return currently active in-flight slots for a domain."""
        domain = extract_domain(domain_or_url)
        with self._state_guard:
            return self._active_counts.get(domain, 0)

    def last_request_time(self, domain_or_url: str) -> float | None:
        """Return monotonic timestamp of the last acquired request slot for a domain."""
        domain = extract_domain(domain_or_url)
        with self._state_guard:
            return self._last_request_at.get(domain)

    def _get_async_primitives(self, domain: str) -> tuple[asyncio.Semaphore, asyncio.Lock]:
        with self._state_guard:
            sem = self._domain_async_sems.get(domain)
            if sem is None:
                sem = asyncio.Semaphore(self.max_concurrent_per_domain)
                self._domain_async_sems[domain] = sem
            lock = self._domain_async_locks.get(domain)
            if lock is None:
                lock = asyncio.Lock()
                self._domain_async_locks[domain] = lock
            return sem, lock

    def _get_sync_primitives(self, domain: str) -> tuple[threading.Semaphore, threading.Lock]:
        with self._state_guard:
            sem = self._domain_sync_sems.get(domain)
            if sem is None:
                sem = threading.Semaphore(self.max_concurrent_per_domain)
                self._domain_sync_sems[domain] = sem
            lock = self._domain_sync_locks.get(domain)
            if lock is None:
                lock = threading.Lock()
                self._domain_sync_locks[domain] = lock
            return sem, lock

    @asynccontextmanager
    async def acquire(self, url_or_domain: str) -> AsyncIterator[str]:
        """Acquire a rate-limited, concurrency-bounded async slot for the target domain."""
        domain = extract_domain(url_or_domain) or "default"
        domain_sem, cooldown_lock = self._get_async_primitives(domain)
        cooldown = self.get_cooldown(domain)

        async with self._global_async_sem, domain_sem:
            async with cooldown_lock:
                if cooldown > 0:
                    last = self._last_request_at.get(domain)
                    if last is not None:
                        elapsed = self._clock() - last
                        remaining = cooldown - elapsed
                        if remaining > 0:
                            await self._async_sleep(remaining)
                self._last_request_at[domain] = self._clock()

            with self._state_guard:
                self._active_counts[domain] += 1
            try:
                yield domain
            finally:
                with self._state_guard:
                    self._active_counts[domain] = max(0, self._active_counts[domain] - 1)

    @contextmanager
    def acquire_sync(self, url_or_domain: str) -> Iterator[str]:
        """Acquire a rate-limited, concurrency-bounded sync slot for the target domain."""
        domain = extract_domain(url_or_domain) or "default"
        domain_sem, cooldown_lock = self._get_sync_primitives(domain)
        cooldown = self.get_cooldown(domain)

        with self._global_sync_sem, domain_sem:
            with cooldown_lock:
                if cooldown > 0:
                    last = self._last_request_at.get(domain)
                    if last is not None:
                        elapsed = self._clock() - last
                        remaining = cooldown - elapsed
                        if remaining > 0:
                            self._sync_sleep(remaining)
                self._last_request_at[domain] = self._clock()

            with self._state_guard:
                self._active_counts[domain] += 1
            try:
                yield domain
            finally:
                with self._state_guard:
                    self._active_counts[domain] = max(0, self._active_counts[domain] - 1)
