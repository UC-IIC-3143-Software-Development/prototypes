import re
from typing import List


class RoundRobinLoadBalancer:
    def __init__(self, public_domain: str, servers: List[str]):
        self.public_domain = public_domain
        self.domain_pattern = re.compile(f"http://{re.escape(public_domain)}")
        self.servers = servers
        self.current_index = 0

    def get_next_server(self) -> str:
        server = self.servers[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.servers)
        return server

    def route_request(self, request: str) -> str:
        server = self.get_next_server()
        return self.domain_pattern.sub(server, request)


def simulate_requests(
    load_balancer: RoundRobinLoadBalancer, requests: List[str]
) -> None:
    print("Available Servers:")
    for server in load_balancer.servers:
        print(f"  {server}")
    print()

    for request in requests:
        print(f"Original request: {request}")
        routed_request = load_balancer.route_request(request)
        print(f"Routed request:   {routed_request}")
        print()


if __name__ == "__main__":
    PUBLIC_DOMAIN = "myblogs.com"
    SERVERS = [
        "http://192.168.0.10",
        "http://192.168.0.11",
        "http://192.168.0.12",
    ]

    load_balancer = RoundRobinLoadBalancer(PUBLIC_DOMAIN, SERVERS)

    sample_requests = [
        f"GET http://{PUBLIC_DOMAIN}/article/123?user_id=5 HTTP/1.1",
        f"POST http://{PUBLIC_DOMAIN}/submit?user_id=15 HTTP/1.1",
        f"GET http://{PUBLIC_DOMAIN}/images/logo.png HTTP/1.1",
        f"GET http://{PUBLIC_DOMAIN}/article/456?user_id=25 HTTP/1.1",
        f"GET http://{PUBLIC_DOMAIN}/about?user_id=35 HTTP/1.1",
    ]

    simulate_requests(load_balancer, sample_requests)
