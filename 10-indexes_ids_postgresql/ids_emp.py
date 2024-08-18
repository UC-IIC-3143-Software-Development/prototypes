import random
import uuid
from datetime import datetime

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

DB_NAME = "employee_db"
DB_USER = "postgres"
DB_PASSWORD = "password"
DB_HOST = "localhost"
DB_PORT = "5432"


def clean_database():
    conn = psycopg2.connect(
        dbname="postgres",
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()

    cursor.execute(
        """
    SELECT pg_terminate_backend(pg_stat_activity.pid)
    FROM pg_stat_activity
    WHERE pg_stat_activity.datname = 'employee_db'
    AND pid <> pg_backend_pid();
    """
    )

    cursor.execute("DROP DATABASE IF EXISTS employee_db")
    cursor.execute("CREATE DATABASE employee_db")

    cursor.close()
    conn.close()

    print("Base de datos limpiada y recreada.")


def generate_rut():
    while True:
        num = random.randint(1000000, 25000000)
        verificador = random.choice([str(i) for i in range(10)] + ["K"])
        rut = f"{num}-{verificador}"
        if rut not in used_ruts:
            used_ruts.add(rut)
            return rut


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
        CREATE TABLE employees_rut (
            rut VARCHAR(12) PRIMARY KEY,
            nombre VARCHAR(100),
            salario INTEGER
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE employees_id (
            id SERIAL PRIMARY KEY,
            rut VARCHAR(12) UNIQUE,
            nombre VARCHAR(100),
            salario INTEGER
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE employees_uuid (
            id UUID PRIMARY KEY,
            rut VARCHAR(12) UNIQUE,
            nombre VARCHAR(100),
            salario INTEGER
        )
    """
    )
    print("Insertando datos...")
    for _ in range(100000):
        rut = generate_rut()
        nombre = f"Empleado {_}"
        salario = random.randint(300000, 5000000)
        uuid_val = str(uuid.uuid4())

        cursor.execute(
            "INSERT INTO employees_rut (rut, nombre, salario) VALUES (%s, %s, %s)",
            (rut, nombre, salario),
        )
        cursor.execute(
            "INSERT INTO employees_id (rut, nombre, salario) VALUES (%s, %s, %s)",
            (rut, nombre, salario),
        )
        cursor.execute(
            "INSERT INTO employees_uuid (id, rut, nombre, salario) VALUES (%s, %s, %s, %s)",
            (uuid_val, rut, nombre, salario),
        )

    conn.commit()
    cursor.close()
    conn.close()

    # Realizar VACUUM ANALYZE
    print("\nRealizando VACUUM ANALYZE...")
    conn = psycopg2.connect(
        dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()

    cursor.execute("VACUUM ANALYZE employees_rut")
    cursor.execute("VACUUM ANALYZE employees_id")
    cursor.execute("VACUUM ANALYZE employees_uuid")

    cursor.close()
    conn.close()

    # Reconectar para continuar con las consultas
    conn = psycopg2.connect(
        dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT
    )
    cursor = conn.cursor()

    # Análisis de distribución de datos
    print("\nAnálisis de distribución de datos:")
    cursor.execute("SELECT MIN(rut), MAX(rut), COUNT(DISTINCT rut) FROM employees_rut")
    min_rut, max_rut, distinct_rut = cursor.fetchone()
    print(f"RUT - Min: {min_rut}, Max: {max_rut}, Distinct: {distinct_rut}")

    cursor.execute("SELECT MIN(id), MAX(id), COUNT(DISTINCT id) FROM employees_id")
    min_id, max_id, distinct_id = cursor.fetchone()
    print(f"ID - Min: {min_id}, Max: {max_id}, Distinct: {distinct_id}")

    # Estadísticas de los índices
    print("\nEstadísticas de los índices:")
    cursor.execute(
        "SELECT null_frac, n_distinct, avg_width FROM pg_stats WHERE tablename = 'employees_rut' AND attname = 'rut'"
    )
    null_frac, n_distinct, avg_width = cursor.fetchone()
    print(
        f"RUT - Null Fraction: {null_frac}, Distinct Values: {n_distinct}, Average Width: {avg_width}"
    )

    cursor.execute(
        "SELECT null_frac, n_distinct, avg_width FROM pg_stats WHERE tablename = 'employees_id' AND attname = 'id'"
    )
    null_frac, n_distinct, avg_width = cursor.fetchone()
    print(
        f"ID - Null Fraction: {null_frac}, Distinct Values: {n_distinct}, Average Width: {avg_width}"
    )

    # Consultas de rendimiento y tamaños
    print("\nConsulta por RUT PK (employees_rut):")
    count, time = run_query(
        cursor, "SELECT * FROM employees_rut WHERE rut = %s", (generate_rut(),)
    )
    print(f"Se encontraron {count} registros en {time:.6f} segundos")

    print("\nConsulta por RUT ID SERIAL (employees_id):")
    count, time = run_query(
        cursor, "SELECT * FROM employees_id WHERE rut = %s", (generate_rut(),)
    )
    print(f"Se encontraron {count} registros en {time:.6f} segundos")

    print("\nConsulta por RUT UUID (employees_uuid):")
    count, time = run_query(
        cursor, "SELECT * FROM employees_uuid WHERE rut = %s", (generate_rut(),)
    )
    print(f"Se encontraron {count} registros en {time:.6f} segundos")

    print("\nConsulta por ID SERIAL (employees_id):")
    count, time = run_query(
        cursor, "SELECT * FROM employees_id WHERE id = %s", (random.randint(1, 100000),)
    )
    print(f"Se encontraron {count} registros en {time:.6f} segundos")

    print("\nConsulta por UUID (employees_uuid):")
    cursor.execute("SELECT id FROM employees_uuid LIMIT 1")
    random_uuid = cursor.fetchone()[0]
    count, time = run_query(
        cursor, "SELECT * FROM employees_uuid WHERE id = %s", (random_uuid,)
    )
    print(f"Se encontraron {count} registros en {time:.6f} segundos")

    cursor.execute("SELECT pg_size_pretty(pg_total_relation_size('employees_rut'))")
    print(f"\nTamaño total de employees_rut: {cursor.fetchone()[0]}")

    cursor.execute("SELECT pg_size_pretty(pg_total_relation_size('employees_id'))")
    print(f"Tamaño total de employees_id: {cursor.fetchone()[0]}")

    cursor.execute("SELECT pg_size_pretty(pg_total_relation_size('employees_uuid'))")
    print(f"Tamaño total de employees_uuid: {cursor.fetchone()[0]}")

    cursor.execute("SELECT pg_size_pretty(pg_indexes_size('employees_rut'))")
    print(f"Tamaño de índices de employees_rut: {cursor.fetchone()[0]}")

    cursor.execute("SELECT pg_size_pretty(pg_indexes_size('employees_id'))")
    print(f"Tamaño de índices de employees_id: {cursor.fetchone()[0]}")

    cursor.execute("SELECT pg_size_pretty(pg_indexes_size('employees_uuid'))")
    print(f"Tamaño de índices de employees_uuid: {cursor.fetchone()[0]}")

    conn.close()


if __name__ == "__main__":
    used_ruts = set()
    main()
