CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    price NUMERIC(10, 2) NOT NULL
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL,
    total NUMERIC(10, 2) NOT NULL,
    status TEXT NOT NULL DEFAULT 'created',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO products (name, price) VALUES
    ('Mechanical Keyboard', 89.99),
    ('USB-C Hub', 39.50),
    ('27-inch Monitor', 249.00),
    ('Wireless Mouse', 24.99);
