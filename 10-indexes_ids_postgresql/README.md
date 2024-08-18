# Indexes PostgreSQL

## Comandos a utilizar

Acceder al container:
docker-compose exec db psql -U postgres -d employee_db


1. Obtener el query plan de alguna consulta SQL:
EXPLAIN SELECT * FROM employees WHERE emp_dob_month = 'may';

2. Analizar una consulta SQL:
EXPLAIN ANALYZE SELECT * FROM employees WHERE emp_dob_month = 'may';

3. Obtener el tamaño del índice:
SELECT pg_size_pretty(pg_relation_size('idx_emp_dob_month'));

4. Consultar

EXPLAIN ANALYZE SELECT * FROM employees_rut WHERE rut = '12345678-K';")
EXPLAIN ANALYZE SELECT * FROM employees_id WHERE rut = '12345678-K';")
EXPLAIN ANALYZE SELECT * FROM employees_uuid WHERE rut = '12345678-K';")
EXPLAIN ANALYZE SELECT * FROM employees_id WHERE id = 50000;")
EXPLAIN ANALYZE SELECT * FROM employees_uuid WHERE id = 'un-uuid-específico';"

5. Realizar un reindex de una tabla

REINDEX TABLE employees_id;
REINDEX TABLE employees_rut;
REINDEX TABLE employees_uuid;

6. Limpiar tuplas muertas (sin uso)

VACUUM ANALYZE employees_rut
VACUUM ANALYZE employees_id
VACUUM ANALYZE employees_uuid
