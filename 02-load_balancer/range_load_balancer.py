import re
from typing import List, Tuple


class RangeByUserIdLoadBalancer:
    def __init__(self, public_domain: str):
        self.public_domain = public_domain
        self.domain_pattern = re.compile(f"http://{re.escape(public_domain)}")
        self.server_ranges = [
            (1, 10, "http://192.168.0.10"),
            (11, 20, "http://192.168.0.11"),
            (21, 30, "http://192.168.0.12"),
        ]

    def get_server_for_user(self, user_id: int) -> str:
        for start, end, server in self.server_ranges:
            if start <= user_id <= end:
                return server
        return (
            # Si userID fuera de rango usar str por default
            "http://default.example.com"
        )

    def route_request(self, request: str) -> str:
        user_id = self._extract_user_id(request)
        if user_id is not None:
            server = self.get_server_for_user(user_id)
            return self.domain_pattern.sub(server, request)
        # Si userID no encontrado return request
        return request

    def _extract_user_id(self, request: str) -> int | None:
        match = re.search(r"user_id=(\d+)", request)
        return int(match.group(1)) if match else None


def simulate_requests(
    load_balancer: RangeByUserIdLoadBalancer, requests: List[str]
) -> None:
    print("Server Ranges:")
    for start, end, server in load_balancer.server_ranges:
        print(f"  {server}: User IDs {start} - {end}")
    print()

    for request in requests:
        print(f"Original request: {request}")
        routed_request = load_balancer.route_request(request)
        print(f"Routed request:   {routed_request}")
        user_id = load_balancer._extract_user_id(request)
        if user_id is not None:
            server = load_balancer.get_server_for_user(user_id)
            print(f"User ID: {user_id}, Routed to: {server}")
        else:
            print("No user ID found in request")
        print()


if __name__ == "__main__":
    PUBLIC_DOMAIN = "myblogs.com"

    load_balancer = RangeByUserIdLoadBalancer(PUBLIC_DOMAIN)

    sample_requests = [
        f"GET http://{PUBLIC_DOMAIN}/article/123?user_id=5 HTTP/1.1",
        f"POST http://{PUBLIC_DOMAIN}/submit?user_id=15 HTTP/1.1",
        f"GET http://{PUBLIC_DOMAIN}/images/logo.png HTTP/1.1",
        f"GET http://{PUBLIC_DOMAIN}/article/456?user_id=25 HTTP/1.1",
        f"GET http://{PUBLIC_DOMAIN}/about?user_id=35 HTTP/1.1",
    ]

    simulate_requests(load_balancer, sample_requests)
