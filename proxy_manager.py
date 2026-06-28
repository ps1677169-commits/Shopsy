import random
import aiohttp
from aiohttp_socks import ProxyConnector
from typing import List, Optional

class ProxyManager:
    def __init__(self):
        self.proxies: List[str] = []
        self.current_index = 0
        self.bad_proxies = set()

    def load_from_file(self, file_path: str) -> int:
        """Load proxies from a text file (one per line). Returns count added."""
        try:
            with open(file_path, 'r') as f:
                lines = [line.strip() for line in f if line.strip()]
            # Filter out duplicates
            new_proxies = [p for p in lines if p not in self.proxies and p not in self.bad_proxies]
            self.proxies.extend(new_proxies)
            return len(new_proxies)
        except Exception as e:
            raise Exception(f"Failed to load proxies: {e}")

    def clear(self):
        self.proxies.clear()
        self.bad_proxies.clear()
        self.current_index = 0

    def get_count(self) -> int:
        return len(self.proxies)

    def get_proxy(self) -> Optional[str]:
        """Get the next available proxy (rotation)."""
        if not self.proxies:
            return None
        # Find a non-bad proxy
        for _ in range(len(self.proxies)):
            proxy = self.proxies[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.proxies)
            if proxy not in self.bad_proxies:
                return proxy
        return None

    def mark_bad(self, proxy: str):
        """Mark a proxy as bad so it won't be used again."""
        if proxy in self.proxies:
            self.proxies.remove(proxy)
            self.bad_proxies.add(proxy)
            # Reset index to avoid out-of-range
            if self.current_index >= len(self.proxies):
                self.current_index = 0

    def get_connector(self, proxy: str):
        """Create an aiohttp connector for the given proxy."""
        if not proxy:
            return None
        # Proxy format: http://user:pass@host:port or host:port
        if '://' not in proxy:
            proxy = 'http://' + proxy
        # Detect SOCKS vs HTTP
        if proxy.startswith('socks5://'):
            return ProxyConnector.from_url(proxy)
        else:
            # For HTTP/HTTPS, use aiohttp TCPConnector with proxy
            # aiohttp does not support proxy directly via connector, but we can pass proxy via session
            return None  # handled separately

    def get_proxy_dict(self, proxy: str):
        """Return a dict for aiohttp proxy parameter."""
        if not proxy:
            return None
        if '://' not in proxy:
            proxy = 'http://' + proxy
        return {'http': proxy, 'https': proxy}
