import mysql.connector
from faker import Faker

db_config = {
    "host": "localhost",
    "user": "root",
    "password": "password",
    "database": "flight_db",
}

SEAT_LAYOUT = [[f"{row}{seat}" for seat in "ABCDEF"] for row in range(1, 25)]

# Create a Faker instance for Spanish names
fake = Faker("en_US")

# En caso de usar Connection Pool
# connection_pool = pooling.MySQLConnectionPool(pool_name="flight_pool",
#                                              pool_size=32,
#                                              **db_config)

# def get_connection():
#    return connection_pool.get_connection()


def setup_database():
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    try:
        # Disable foreign key checks
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

        # Truncate both tables
        cursor.execute("TRUNCATE TABLE seats")
        cursor.execute("TRUNCATE TABLE users")

        # Re-enable foreign key checks
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

        # Insert seats
        for row in SEAT_LAYOUT:
            for seat in row:
                cursor.execute("INSERT INTO seats (seat_number) VALUES (%s)", (seat,))

        conn.commit()
    except mysql.connector.Error as error:
        print(f"Error setting up database: {error}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def generate_users(num_users):
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    users = []
    try:
        for _ in range(num_users):
            first_name = fake.first_name()
            last_name = fake.last_name()
            cursor.execute(
                "INSERT INTO users (first_name, last_name) VALUES (%s, %s)",
                (first_name, last_name),
            )
            user_id = cursor.lastrowid
            users.append((user_id, f"{first_name} {last_name}"))

        conn.commit()
    except mysql.connector.Error as error:
        print(f"Error generating users: {error}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

    return users


def get_seat_map():
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
        SELECT s.seat_number, CONCAT(u.first_name, ' ', u.last_name) as user_name
        FROM seats s
        LEFT JOIN users u ON s.user_id = u.id
        """
        )
        seats = {seat: user_name for seat, user_name in cursor.fetchall()}

        seat_map = ""
        for row in SEAT_LAYOUT:
            for seat in row:
                if seats[seat]:
                    seat_map += f"{seat}:{seats[seat][:12]:<12} "
                else:
                    seat_map += f"{seat}:Empty   "
            seat_map += "\n"
    except mysql.connector.Error as error:
        print(f"Error getting seat map: {error}")
        seat_map = "Error retrieving seat map"
    finally:
        cursor.close()
        conn.close()

    return seat_map


def print_seats():
    print("\nFinal Seat Map:")
    print(get_seat_map())
