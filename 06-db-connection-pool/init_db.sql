CREATE DATABASE IF NOT EXISTS counter_db;
USE counter_db;

CREATE TABLE IF NOT EXISTS counter (
    id INT PRIMARY KEY,
    value INT NOT NULL
);

INSERT IGNORE INTO counter (id, value) VALUES (1, 0);
