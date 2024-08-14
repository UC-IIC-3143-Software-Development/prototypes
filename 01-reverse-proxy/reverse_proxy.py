import re
from typing import List


class ReverseProxy:
    def __init__(self, public_domain: str, backend_address: str):
        self.public_domain = public_domain
        self.backend_address = backend_address
        self.domain_pattern = re.compile(f"http://{re.escape(self.public_domain)}")

    def process_request(self, request: str) -> str:
        return self.domain_pattern.sub(self.backend_address, request)

    def handle_request(self, request: str) -> str:
        return self.process_request(request)


def simulate_requests(proxy: ReverseProxy, requests: List[str]) -> None:
    for request in requests:
        print(f"Original request: {request}")
        modified = proxy.handle_request(request)
        print(f"Modified request: {modified}")
        print()


if __name__ == "__main__":
    PUBLIC_DOMAIN = "myblogs.com"
    BACKEND_ADDRESS = "http://192.168.0.10"

    proxy = ReverseProxy(PUBLIC_DOMAIN, BACKEND_ADDRESS)

    sample_requests = [
        f"GET http://myblogs.com/article/123 HTTP/1.1",
        f"POST http://myblogs.com/submit HTTP/1.1",
        f"GET http://myblogs.com/images/logo.png HTTP/1.1",
    ]

    simulate_requests(proxy, sample_requests)
