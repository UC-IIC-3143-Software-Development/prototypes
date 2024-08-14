CREATE DATABASE IF NOT EXISTS ecommerce;
USE ecommerce;

CREATE TABLE IF NOT EXISTS products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    price DECIMAL(10, 2) NOT NULL,
    stock INT NOT NULL
);

INSERT INTO products (name, description, price, stock) VALUES
('Laptop', 'High-performance laptop', 999.99, 50),
('Smartphone', 'Latest model smartphone', 699.99, 100),
('Headphones', 'Noise-cancelling headphones', 199.99, 200),
('Tablet', '10-inch tablet', 299.99, 75),
('Smartwatch', 'Fitness tracking smartwatch', 149.99, 150);
