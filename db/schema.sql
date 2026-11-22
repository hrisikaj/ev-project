CREATE TABLE IF NOT EXISTS lots (
    lot_id STRING PRIMARY KEY,
    lot_name STRING NOT NULL,
    city STRING NOT NULL CHECK (city IN ('city1', 'city2', 'city3'))
);

CREATE TABLE IF NOT EXISTS ports (
    port_id STRING PRIMARY KEY,
    lot_id STRING NOT NULL REFERENCES lots (lot_id),
    home_city STRING NOT NULL CHECK (home_city IN ('city1', 'city2', 'city3')),
    booking_city STRING NOT NULL CHECK (booking_city IN ('city1', 'city2', 'city3'))
);

CREATE TABLE IF NOT EXISTS reservations (
    r_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    port_id STRING NOT NULL REFERENCES ports (port_id),
    u_id INT NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    booked_by STRING NOT NULL CHECK (booked_by IN ('city1', 'city2', 'city3')),
    CHECK (end_time > start_time),
    INDEX idx_res_port_time (port_id, start_time, end_time)
);

CREATE TABLE IF NOT EXISTS requests (
    req_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    u_id INT NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL,
    home_city STRING NOT NULL CHECK (home_city IN ('city1', 'city2', 'city3')),
    handled_by STRING NOT NULL CHECK (handled_by IN ('city1', 'city2', 'city3')),
    redirect_count INT NOT NULL DEFAULT 0,
    retries INT NOT NULL DEFAULT 0,
    status STRING NOT NULL CHECK (status IN ('accepted', 'rejected')),
    reject_reason STRING,
    r_id UUID
);