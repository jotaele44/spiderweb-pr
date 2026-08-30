CREATE TABLE IF NOT EXISTS flights (
    flight_id TEXT PRIMARY KEY,
    callsign TEXT,
    aircraft_type TEXT,
    operator TEXT,
    origin_airport TEXT,
    destination_airport TEXT,
    origin_lat REAL,
    origin_lon REAL,
    dest_lat REAL,
    dest_lon REAL,
    takeoff_time TEXT,
    landing_time TEXT,
    flight_duration_minutes INTEGER,
    max_altitude_ft INTEGER,
    avg_speed_mph REAL,
    mission_type TEXT,
    num_screenshots INTEGER
);

CREATE TABLE IF NOT EXISTS track_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    flight_id TEXT,
    timestamp TEXT,
    latitude REAL,
    longitude REAL,
    altitude_ft INTEGER,
    ground_speed_mph INTEGER
);
