import random
from datetime import datetime

import psycopg2

DB_NAME = "employee_db"
DB_USER = "postgres"
DB_PASSWORD = "password"
DB_HOST = "localhost"
DB_PORT = "5432"


def clean_database():
    conn = psycopg2.connect(
        dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT
    )
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS employees")

    cursor.execute("DROP INDEX IF EXISTS idx_emp_dob_month")

    conn.close()
    print("Base de datos limpiada.")


def run_query(cursor, query, params=None):
    start_time = datetime.now()
    if params:
        cursor.execute(query, params)
    else:
        cursor.execute(query)
    results = cursor.fetchall()
    end_time = datetime.now()
    return len(results), (end_time - start_time).total_seconds()


def main():
    clean_database()

    conn = psycopg2.connect(
        dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT
    )
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE employees (
            emp_id INTEGER PRIMARY KEY,
            emp_name VARCHAR(100),
            emp_dob_month VARCHAR(20),
            emp_salary INTEGER
        )
    """
    )

    # Generar e insertar datos aleatorios
    months = [
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    ]
    names = [
        "John",
        "Jane",
        "Alice",
        "Bob",
        "Charlie",
        "Diana",
        "Edward",
        "Fiona",
        "George",
        "Hannah",
    ]

    for i in range(1, 10000):
        emp_id = i
        emp_name = random.choice(names) + " " + random.choice(names)
        emp_dob_month = random.choice(months)
        emp_salary = random.randint(1000, 10000)
        cursor.execute(
            """
            INSERT INTO employees (emp_id, emp_name, emp_dob_month, emp_salary)
            VALUES (%s, %s, %s, %s)
        """,
            (emp_id, emp_name, emp_dob_month, emp_salary),
        )
    conn.commit()
    print("Datos insertados en la tabla 'employees'.")

    print("\Query sin index")
    count, time = run_query(
        cursor, "SELECT * FROM employees WHERE emp_dob_month = %s", ("may",)
    )
    print(f"Se encontraron {count} registros en {time:.4f} segundos")

    cursor.execute("CREATE INDEX idx_emp_dob_month ON employees(emp_dob_month)")
    conn.commit()
    print("Index creado en la columna emp_dob_month.")

    # Consulta con índice
    print("\nQuery con index:")
    count, time = run_query(
        cursor, "SELECT * FROM employees WHERE emp_dob_month = %s", ("may",)
    )
    print(f"Se encontraron {count} registros en {time:.4f} segundos")

    # Cerrar conexión
    conn.close()


if __name__ == "__main__":
    main()
