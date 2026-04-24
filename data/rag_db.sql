CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE residents (
    id INTEGER PRIMARY KEY,
    name TEXT,
    flat_no TEXT,
    age INTEGER,
    health_medical_history TEXT,
    medical_intake_prescribed TEXT
);

CREATE TABLE health_reports (
    resident_id INTEGER,
    bp_systolic INTEGER,
    bp_diastolic INTEGER,
    sugar_level NUMERIC,
    recorded_at TIMESTAMP,
    FOREIGN KEY (resident_id) REFERENCES residents(id)
);

CREATE TABLE activity_metrics (
    resident_id INTEGER,
    steps_count INTEGER,
    recorded_at TIMESTAMP,
    FOREIGN KEY (resident_id) REFERENCES residents(id)
);

CREATE TABLE sleep_analytics (
    resident_id INTEGER,
    sleep_duration_minutes INTEGER,
    sleep_quality_score INTEGER,
    recorded_at TIMESTAMP,
    FOREIGN KEY (resident_id) REFERENCES residents(id)
);

CREATE TABLE device_status (
    board_id TEXT,
    location TEXT,
    signal NUMERIC,
    uptime NUMERIC,
    cpu NUMERIC,
    time TIMESTAMP
);

CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    content TEXT,
    embedding VECTOR(1024),
    metadata JSONB
);

INSERT INTO residents (id, name, flat_no, age, health_medical_history, medical_intake_prescribed) VALUES
(1, 'John Mathew', 'A-101', 78, 'Hypertension, Type 2 Diabetes', 'Metformin, Amlodipine'),
(2, 'Mary Dsouza', 'A-102', 82, 'Arthritis, Mild Asthma', 'Paracetamol, Salbutamol'),
(3, 'Ravi Kumar', 'B-201', 74, 'Cardiovascular disease', 'Atorvastatin, Aspirin'),
(4, 'Jason Murphy', 'B-202', 80, 'Osteoporosis', 'Calcium, Vitamin D'),
(5, 'Anil Sharma', 'C-301', 69, 'Pre-diabetes, Hypertension', 'Telmisartan');

INSERT INTO health_reports (resident_id, bp_systolic, bp_diastolic, sugar_level, recorded_at) VALUES
(1, 148, 92, 182.5, '2026-04-18 08:30:00'),
(2, 132, 84, 118.0, '2026-04-18 09:00:00'),
(3, 156, 96, 140.2, '2026-04-18 09:30:00'),
(4, 128, 80, 108.4, '2026-04-18 10:00:00'),
(5, 142, 90, 165.1, '2026-04-18 10:30:00');

INSERT INTO activity_metrics (resident_id, steps_count, recorded_at) VALUES
(1, 3200, '2026-04-18 20:00:00'),
(2, 4100, '2026-04-18 20:00:00'),
(3, 2500, '2026-04-18 20:00:00'),
(4, 5300, '2026-04-18 20:00:00'),
(5, 2900, '2026-04-18 20:00:00');

INSERT INTO sleep_analytics (resident_id, sleep_duration_minutes, sleep_quality_score, recorded_at) VALUES
(1, 360, 58, '2026-04-19 06:30:00'),
(2, 420, 74, '2026-04-19 06:30:00'),
(3, 310, 49, '2026-04-19 06:30:00'),
(4, 455, 81, '2026-04-19 06:30:00'),
(5, 340, 55, '2026-04-19 06:30:00');

INSERT INTO device_status (board_id, location, signal, uptime, cpu, time) VALUES
('DEV1', 'Ward A', -67.5, 99.1, 41.2, '2026-04-19 11:00:00'),
('DEV2', 'Ward B', -72.0, 97.8, 46.5, '2026-04-19 11:00:00'),
('DEV3', 'ICU', -61.3, 99.7, 38.4, '2026-04-19 11:00:00'),
('DEV4', 'Lobby', -80.1, 94.2, 52.8, '2026-04-19 11:00:00'),
('DEV5', 'Pharmacy', -69.4, 98.6, 43.9, '2026-04-19 11:00:00');

SELECT id, content, metadata -- to check the chunks
FROM documents
ORDER BY id;

TRUNCATE TABLE documents RESTART IDENTITY; -- to remove duplicates and start from first

SELECT id, embedding IS NOT NULL AS has_embedding -- to check if embeddings exist
FROM documents
ORDER BY id;

SELECT id, embedding -- to check the actual vector values
FROM documents
ORDER BY id
LIMIT 5;

SELECT id, content --to check similarity
FROM documents
ORDER BY embedding <-> (
    SELECT embedding
    FROM documents
    LIMIT 1
)
LIMIT 5;









