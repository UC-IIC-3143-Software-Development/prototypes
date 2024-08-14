import json
import random
import time
from decimal import Decimal

import mysql.connector
import redis

# MySQL connection
mysql_config = {
    "user": "root",
    "password": "password",
    "host": "localhost",
    "database": "ecommerce",
}

# Redis connection
redis_client = redis.Redis(host="localhost", port=6379, db=0)


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)


def get_product_from_db(product_id):
    try:
        conn = mysql.connector.connect(**mysql_config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
        product = cursor.fetchone()
        cursor.close()
        conn.close()
        return product
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return None


def get_product(product_id):
    # Try to get the product from Redis (hot storage)
    cached_product = redis_client.get(f"product:{product_id}")

    if cached_product:
        print(f"Product {product_id} found in cache (hot storage - Redis)")
        return json.loads(cached_product)
    else:
        print(
            f"Product {product_id} not in cache, fetching from database (cold storage - MySQL)"
        )
        # If not in Redis, get from MySQL (cold storage)
        product = get_product_from_db(product_id)
        if product:
            # Store in Redis for future quick access
            redis_client.setex(
                f"product:{product_id}", 3600, json.dumps(product, cls=DecimalEncoder)
            )
        return product


def simulate_product_views():
    total_products = 5  # Assuming we have 5 products in our database
    view_counts = {i: 0 for i in range(1, total_products + 1)}

    for _ in range(10):  # Simulate 100 product views
        # Simulate some products being viewed more frequently
        product_id = random.choices(
            range(1, total_products + 1), weights=[50, 30, 10, 5, 5]
        )[0]

        start_time = time.time()
        product = get_product(product_id)
        end_time = time.time()

        if product:
            view_counts[product_id] += 1
            print(
                f"Retrieved product {product_id} in {(end_time - start_time)*1000:.2f} ms"
            )
        else:
            print(f"Product {product_id} not found")

        time.sleep(0.01)  # Small delay between views

    print("\nProduct view counts:")
    for product_id, count in view_counts.items():
        print(f"Product {product_id}: {count} views")


if __name__ == "__main__":
    simulate_product_views()
