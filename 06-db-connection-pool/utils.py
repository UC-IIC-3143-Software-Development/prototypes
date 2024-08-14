import mysql.connector
from mysql.connector import pooling

db_config = {
    "host": "localhost",
    "user": "root",
    "password": "password",
    "database": "counter_db",
}

# Create a connection pool
connection_pool = pooling.MySQLConnectionPool(
    pool_name="counter_pool", pool_size=32, **db_config
)


def get_pooled_connection():
    return connection_pool.get_connection()


def get_non_pooled_connection():
    return mysql.connector.connect(**db_config)


def setup_database():
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS counter (
            id INT PRIMARY KEY,
            value INT NOT NULL
        )
        """
        )

        cursor.execute("INSERT IGNORE INTO counter (id, value) VALUES (1, 0)")

        conn.commit()
    except mysql.connector.Error as error:
        print(f"Error setting up database: {error}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def reset_counter():
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    try:
        cursor.execute("UPDATE counter SET value = 0 WHERE id = 1")
        conn.commit()
    except mysql.connector.Error as error:
        print(f"Error resetting counter: {error}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def get_counter_value():
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT value FROM counter WHERE id = 1")
        return cursor.fetchone()[0]
    except mysql.connector.Error as error:
        print(f"Error getting counter value: {error}")
        return None
    finally:
        cursor.close()
        conn.close()
