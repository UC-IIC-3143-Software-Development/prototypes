import random
from typing import List, Tuple


class CacheDebounce:
    def __init__(self, cache_percentage: float):
        if not 0 <= cache_percentage <= 100:
            raise ValueError("Cache percentage must be between 0 and 100")

        self.cache_percentage = cache_percentage
        self.cache_server = "redis://cache.myblogs.com"
        self.db_server = "postgresql://db.myblogs.com"

    def route_request(self, request: str) -> Tuple[str, str]:
        if random.random() * 100 < self.cache_percentage:
            destination = f"Cache: {self.cache_server}"
        else:
            destination = f"Database: {self.db_server}"

        return (destination, request)


def simulate_requests(debouncer: CacheDebounce, num_requests: int) -> None:
    print(f"Cache Server: {debouncer.cache_server}")
    print(f"Database Server: {debouncer.db_server}")
    print(f"Cache Percentage: {debouncer.cache_percentage}%")
    print(f"Number of Requests: {num_requests}")
    print()

    cache_count = 0
    db_count = 0

    for i in range(num_requests):
        request = f"GET /article/{i}"
        routed_to, _ = debouncer.route_request(request)

        if routed_to.startswith("Cache"):
            cache_count += 1
        else:
            db_count += 1

    print(f"Total Requests: {num_requests}")
    print(f"Requests to Cache: {cache_count} ({cache_count/num_requests*100:.2f}%)")
    print(f"Requests to Database: {db_count} ({db_count/num_requests*100:.2f}%)")


if __name__ == "__main__":
    CACHE_PERCENTAGE = 30  # 30% requests va a cache
    NUM_REQUESTS = 100000
    # Asegurar resultado reproducible con un fixed seed
    # RANDOM_SEED = 42
    # random.seed(RANDOM_SEED)
    debouncer = CacheDebounce(CACHE_PERCENTAGE)

    simulate_requests(debouncer, NUM_REQUESTS)
