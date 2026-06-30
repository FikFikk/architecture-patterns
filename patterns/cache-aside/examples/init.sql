-- Initialize test database for cache-aside pattern demo

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

-- Insert sample data
INSERT INTO users (name, email, created_at) VALUES
    ('Alice Johnson', 'alice@example.com', NOW() - INTERVAL '30 days'),
    ('Bob Smith', 'bob@example.com', NOW() - INTERVAL '25 days'),
    ('Charlie Brown', 'charlie@example.com', NOW() - INTERVAL '20 days'),
    ('Diana Prince', 'diana@example.com', NOW() - INTERVAL '15 days'),
    ('Eve Wilson', 'eve@example.com', NOW() - INTERVAL '10 days'),
    ('Frank Castle', 'frank@example.com', NOW() - INTERVAL '5 days'),
    ('Grace Hopper', 'grace@example.com', NOW() - INTERVAL '3 days'),
    ('Henry Ford', 'henry@example.com', NOW() - INTERVAL '2 days'),
    ('Iris West', 'iris@example.com', NOW() - INTERVAL '1 day'),
    ('Jack Ryan', 'jack@example.com', NOW());

-- Create index
CREATE INDEX idx_users_email ON users(email);

-- Show initial data
SELECT 'Initial users count:' as info, COUNT(*) as count FROM users;
