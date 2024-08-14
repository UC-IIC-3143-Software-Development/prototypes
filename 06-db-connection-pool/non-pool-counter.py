import threading
import time

from utils import (get_counter_value, get_non_pooled_connection, reset_counter,
                   setup_database)


def increment_counter(user_id):
    try:
        conn = get_non_pooled_connection()
        cursor = conn.cursor()

        cursor.execute("UPDATE counter SET value = value + 1 WHERE id = 1")
        conn.commit()

        print(f"User {user_id} incremented the counter")
    except Exception as error:
        print(f"Error for user {user_id}: {error}")
    finally:
        cursor.close()
        conn.close()


def main():
    setup_database()
    reset_counter()

    # Conexiones maximas en mysql es de 151 by default (150 + 1 for root user)
    num_users = 200
    threads = []

    start_time = time.time()

    for i in range(num_users):
        thread = threading.Thread(target=increment_counter, args=(i,))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    end_time = time.time()

    final_value = get_counter_value()
    print(f"\nFinal counter value: {final_value}")
    print(f"Total time taken: {end_time - start_time:.2f} seconds")


if __name__ == "__main__":
    main()
