FROM mysql:8.0

ENV MYSQL_ROOT_PASSWORD=password
ENV MYSQL_DATABASE=counter_db

COPY init_db.sql /docker-entrypoint-initdb.d/

EXPOSE 3306
