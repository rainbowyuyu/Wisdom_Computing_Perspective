"""Small bounded request limiter for a single-process public workbench."""
from collections import OrderedDict, deque
import time


class PublicLimiter:
    def __init__(self, limit=60, window=60, capacity=2048):
        self.limit = limit
        self.window = window
        self.capacity = capacity
        self.entries = OrderedDict()

    def allow(self, key, now=None):
        now = time.monotonic() if now is None else now
        while self.entries:
            first = next(iter(self.entries))
            if self.entries[first][-1] > now - self.window:
                break
            self.entries.popitem(last=False)
        queue = self.entries.get(key)
        if queue is None:
            # Reject new identities when full; never evict a live budget.
            if len(self.entries) >= self.capacity:
                return False
            queue = self.entries[key] = deque()
        while queue and queue[0] <= now - self.window:
            queue.popleft()
        if len(queue) >= self.limit:
            return False
        queue.append(now)
        self.entries.move_to_end(key)
        return True
