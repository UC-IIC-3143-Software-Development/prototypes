import threading
import time

import mysql.connector
from utils import db_config, generate_users, print_seats, setup_database


def book(user_id, user_name):
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    try:
        cursor.execute("START TRANSACTION")
        # FOR UPDATE SKIP LOCKED: Pessimistic locking with skip
        cursor.execute(
            """
            SELECT id, seat_number FROM seats
            WHERE user_id IS NULL
            ORDER BY id LIMIT 1
            FOR UPDATE SKIP LOCKED
        """
        )
        result = cursor.fetchone()
        if result:
            seat_id, seat_number = result
            cursor.execute(
                "UPDATE seats SET user_id = %s WHERE id = %s", (user_id, seat_id)
            )
            cursor.execute("COMMIT")
            print(f"{user_name} was assigned seat {seat_number}")
            return seat_number, user_name
        else:
            print(f"No seat available for {user_name}")
            cursor.execute("COMMIT")
            return None, user_name
    except mysql.connector.Error as error:
        print(f"Error booking seat for {user_name}: {error}")
        cursor.execute("ROLLBACK")
        return None, user_name
    finally:
        cursor.close()
        conn.close()


def main():
    setup_database()
    # MySQL max_connections is 151 by default (150 + 1 for root user)
    # 150 users for 144 seats
    users = generate_users(150)
    threads = []
    seat_assignments = {}
    start_time = time.time()

    def book_and_record(user_id, user_name):
        result = book(user_id, user_name)
        if result[0]:
            seat_assignments[result[0]] = result[1]

    for user_id, user_name in users:
        thread = threading.Thread(target=book_and_record, args=(user_id, user_name))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    end_time = time.time()

    print("\nFinal Seat Assignments:")
    for seat, name in sorted(seat_assignments.items()):
        print(f"{seat}: {name}")

    print_seats()
    print(f"\nTotal time taken: {end_time - start_time:.2f} seconds")


if __name__ == "__main__":
    main()
