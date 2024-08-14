import hashlib
import re
from typing import List, Optional


class HashBasedLoadBalancer:
    def __init__(self, public_domain: str, backend_addresses: List[str]):
        self.public_domain = public_domain
        self.backend_addresses = backend_addresses
        self.domain_pattern = re.compile(f"http://{re.escape(self.public_domain)}")

    def get_backend_for_key(self, key: str) -> str:
        hash_value = hashlib.md5(key.encode()).hexdigest()
        index = int(hash_value, 16) % len(self.backend_addresses)
        return self.backend_addresses[index]

    def extract_routing_key(self, request: str) -> Optional[str]:
        # Extraer el user ID de request, usar userID como llave
        match = re.search(r"user_id=(\w+)", request)
        if match:
            return match.group(1)

        # Si UserID no existe, usar todo el str de request como llave
        return request

    def process_request(self, request: str) -> str:
        routing_key = self.extract_routing_key(request)
        backend_address = self.get_backend_for_key(routing_key)  # type: ignore
        return self.domain_pattern.sub(backend_address, request)

    def handle_request(self, request: str) -> str:
        return self.process_request(request)


def simulate_requests(
    load_balancer: HashBasedLoadBalancer, requests: List[str]
) -> None:
    for request in requests:
        print(f"Original request: {request}")
        modified = load_balancer.handle_request(request)
        print(f"Modified request: {modified}")
        print(f"Routing key: {load_balancer.extract_routing_key(request)}")
        print()


if __name__ == "__main__":
    PUBLIC_DOMAIN = "myblogs.com"
    BACKEND_ADDRESSES = [
        "http://192.168.0.10",
        "http://192.168.0.11",
        "http://192.168.0.12",
    ]

    load_balancer = HashBasedLoadBalancer(PUBLIC_DOMAIN, BACKEND_ADDRESSES)

    sample_requests = [
        f"GET http://{PUBLIC_DOMAIN}/article/123?user_id=user1 HTTP/1.1",
        f"POST http://{PUBLIC_DOMAIN}/submit?user_id=user2 HTTP/1.1",
        f"GET http://{PUBLIC_DOMAIN}/images/logo.png HTTP/1.1",
        f"GET http://{PUBLIC_DOMAIN}/article/456?user_id=user1 HTTP/1.1",
        f"GET http://{PUBLIC_DOMAIN}/about?user_id=user3 HTTP/1.1",
    ]

    simulate_requests(load_balancer, sample_requests)
