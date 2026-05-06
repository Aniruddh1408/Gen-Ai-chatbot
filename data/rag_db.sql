-- Enable pgvector so PostgreSQL can store and compare embedding vectors.
-- Required for the documents.embedding VECTOR(1024) column and <-> similarity search.
CREATE EXTENSION IF NOT EXISTS vector;


-- Communities isolate resident data by caretaker/community context.
CREATE TABLE communities (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    code TEXT NOT NULL UNIQUE
);


-- Core resident profile table.
-- community_id scopes each resident to one care community.
CREATE TABLE residents (
    id INTEGER PRIMARY KEY,
    community_id INTEGER NOT NULL,
    name TEXT,
    flat_no TEXT,
    age INTEGER,
    health_medical_history TEXT,
    medical_intake_prescribed TEXT,
    FOREIGN KEY (community_id) REFERENCES communities(id)
);


-- Clinical health readings linked to a resident.
-- Community isolation is resolved through residents.community_id.
CREATE TABLE health_reports (
    resident_id INTEGER,
    bp_systolic INTEGER,
    bp_diastolic INTEGER,
    sugar_level NUMERIC,
    recorded_at TIMESTAMP,
    FOREIGN KEY (resident_id) REFERENCES residents(id)
);


-- Activity readings linked to a resident.
-- Used for questions about steps, activity level, and movement comparisons.
CREATE TABLE activity_metrics (
    resident_id INTEGER,
    steps_count INTEGER,
    recorded_at TIMESTAMP,
    FOREIGN KEY (resident_id) REFERENCES residents(id)
);


-- Sleep readings linked to a resident.
-- Higher sleep_quality_score means better sleep quality in this dataset.
CREATE TABLE sleep_analytics (
    resident_id INTEGER,
    sleep_duration_minutes INTEGER,
    sleep_quality_score INTEGER,
    recorded_at TIMESTAMP,
    FOREIGN KEY (resident_id) REFERENCES residents(id)
);


-- Device telemetry table.
-- Stores operational IoT/device status values such as signal, uptime, and CPU.
CREATE TABLE device_status (
    board_id TEXT,
    location TEXT,
    signal NUMERIC,
    uptime NUMERIC,
    cpu NUMERIC,
    time TIMESTAMP
);


-- One row per documentation source file.
-- The ingestion script uses source_hash to detect changed source files.
-- is_active allows removed files to be hidden from RAG without deleting history.
CREATE TABLE document_sources (
    source_id TEXT PRIMARY KEY,
    source_title TEXT,
    source_path TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- Chunk-level documentation table for RAG.
-- Each row stores one chunk of documentation plus its vector embedding.
-- chunk_hash prevents duplicate chunks from being embedded repeatedly.
-- embedding_model prevents mixing vectors from different embedding models.
-- is_active lets retrieval ignore old/deleted chunks while preserving audit history.
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    source_id TEXT,
    source_title TEXT,
    source_path TEXT,
    chunk_index INTEGER,
    chunk_hash TEXT UNIQUE,
    content TEXT,
    embedding VECTOR(1024),
    embedding_model TEXT,
    embedding_dim INTEGER,
    metadata JSONB,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES document_sources(source_id)
);


-- Speeds up community-scoped resident retrieval.
CREATE INDEX residents_community_idx ON residents (community_id);

-- Speeds up latest metric lookup by resident.
CREATE INDEX health_reports_resident_recorded_idx ON health_reports (resident_id, recorded_at DESC);
CREATE INDEX activity_metrics_resident_recorded_idx ON activity_metrics (resident_id, recorded_at DESC);
CREATE INDEX sleep_analytics_resident_recorded_idx ON sleep_analytics (resident_id, recorded_at DESC);

-- Speeds up RAG filtering for active chunks from the current embedding model.
CREATE INDEX documents_active_model_idx ON documents (is_active, embedding_model);

-- Speeds up source-level maintenance, inspection, and deactivation.
CREATE INDEX documents_source_idx ON documents (source_id, is_active);


-- Seed communities for local development and testing.
INSERT INTO communities (id, name, code) VALUES
(1, 'Green Valley Care', 'GREEN_VALLEY'),
(2, 'Sunrise Senior Living', 'SUNRISE'),
(3, 'Lotus Wellness Home', 'LOTUS');


-- Seed 5 residents per community.
INSERT INTO residents
(id, community_id, name, flat_no, age, health_medical_history, medical_intake_prescribed)
VALUES
(1, 1, 'John Mathew', 'A-101', 78, 'Hypertension, Type 2 Diabetes', 'Metformin, Amlodipine'),
(2, 1, 'Mary Dsouza', 'A-102', 82, 'Arthritis, Mild Asthma', 'Paracetamol, Salbutamol'),
(3, 1, 'Ravi Kumar', 'A-103', 74, 'Cardiovascular disease', 'Atorvastatin, Aspirin'),
(4, 1, 'Jason Murphy', 'A-104', 80, 'Osteoporosis', 'Calcium, Vitamin D'),
(5, 1, 'Anil Sharma', 'A-105', 69, 'Pre-diabetes, Hypertension', 'Telmisartan'),

(6, 2, 'Nalini Yadav', 'B-201', 82, 'Hypertension under observation', 'Amlodipine'),
(7, 2, 'Aarav Menon', 'B-202', 65, 'Type 2 Diabetes, controlled', 'Metformin'),
(8, 2, 'Kavya Iyer', 'B-203', 68, 'Mild Asthma', 'Salbutamol inhaler'),
(9, 2, 'Rishi Nambiar', 'B-204', 71, 'Arthritis and joint pain', 'Paracetamol as needed'),
(10, 2, 'Meera Krishnan', 'B-205', 74, 'Cardiac risk monitoring', 'Atorvastatin'),

(11, 3, 'Devendra Patil', 'C-301', 77, 'Post-surgery mobility support', 'Calcium, Vitamin D'),
(12, 3, 'Priya Saxena', 'C-302', 70, 'Thyroid disorder', 'Levothyroxine'),
(13, 3, 'Karan Oberoi', 'C-303', 73, 'Osteoporosis screening', 'Calcium, Vitamin D'),
(14, 3, 'Leela Varma', 'C-304', 76, 'No major chronic illness recorded', 'Routine multivitamin'),
(15, 3, 'Sanjay Trivedi', 'C-305', 79, 'Pre-diabetes and lifestyle monitoring', 'Diet and exercise plan');


-- Seed one health reading per resident.
INSERT INTO health_reports (resident_id, bp_systolic, bp_diastolic, sugar_level, recorded_at) VALUES
(1, 148, 92, 182.5, '2026-04-18 08:30:00'),
(2, 132, 84, 118.0, '2026-04-18 09:00:00'),
(3, 156, 96, 140.2, '2026-04-18 09:30:00'),
(4, 128, 80, 108.4, '2026-04-18 10:00:00'),
(5, 142, 90, 165.1, '2026-04-18 10:30:00'),

(6, 136, 92, 131.9, '2026-04-18 08:30:00'),
(7, 118, 72, 95.0, '2026-04-18 09:00:00'),
(8, 125, 77, 104.1, '2026-04-18 09:30:00'),
(9, 132, 82, 113.2, '2026-04-18 10:00:00'),
(10, 139, 87, 122.3, '2026-04-18 10:30:00'),

(11, 143, 72, 185.0, '2026-04-18 08:30:00'),
(12, 121, 78, 102.0, '2026-04-18 09:00:00'),
(13, 135, 86, 128.4, '2026-04-18 09:30:00'),
(14, 126, 80, 110.5, '2026-04-18 10:00:00'),
(15, 145, 90, 142.8, '2026-04-18 10:30:00');


-- Seed one activity reading per resident.
INSERT INTO activity_metrics (resident_id, steps_count, recorded_at) VALUES
(1, 3200, '2026-04-18 20:00:00'),
(2, 4100, '2026-04-18 20:00:00'),
(3, 2500, '2026-04-18 20:00:00'),
(4, 5300, '2026-04-18 20:00:00'),
(5, 2900, '2026-04-18 20:00:00'),

(6, 2363, '2026-04-18 20:00:00'),
(7, 1800, '2026-04-18 20:00:00'),
(8, 1937, '2026-04-18 20:00:00'),
(9, 2074, '2026-04-18 20:00:00'),
(10, 2211, '2026-04-18 20:00:00'),

(11, 3170, '2026-04-18 20:00:00'),
(12, 3900, '2026-04-18 20:00:00'),
(13, 2800, '2026-04-18 20:00:00'),
(14, 5100, '2026-04-18 20:00:00'),
(15, 2600, '2026-04-18 20:00:00');


-- Seed one sleep reading per resident.
INSERT INTO sleep_analytics (resident_id, sleep_duration_minutes, sleep_quality_score, recorded_at) VALUES
(1, 360, 58, '2026-04-19 06:30:00'),
(2, 420, 74, '2026-04-19 06:30:00'),
(3, 310, 49, '2026-04-19 06:30:00'),
(4, 455, 81, '2026-04-19 06:30:00'),
(5, 340, 55, '2026-04-19 06:30:00'),

(6, 357, 86, '2026-04-19 06:30:00'),
(7, 280, 42, '2026-04-19 06:30:00'),
(8, 303, 53, '2026-04-19 06:30:00'),
(9, 326, 64, '2026-04-19 06:30:00'),
(10, 349, 75, '2026-04-19 06:30:00'),

(11, 290, 42, '2026-04-19 06:30:00'),
(12, 400, 72, '2026-04-19 06:30:00'),
(13, 330, 58, '2026-04-19 06:30:00'),
(14, 430, 80, '2026-04-19 06:30:00'),
(15, 320, 55, '2026-04-19 06:30:00');


-- Seed device telemetry.
-- These rows support SQL questions about device status, signal, uptime, CPU, and location.
INSERT INTO device_status (board_id, location, signal, uptime, cpu, time) VALUES
('DEV1', 'Ward A', -67.5, 99.1, 41.2, '2026-04-19 11:00:00'),
('DEV2', 'Ward B', -72.0, 97.8, 46.5, '2026-04-19 11:00:00'),
('DEV3', 'ICU', -61.3, 99.7, 38.4, '2026-04-19 11:00:00'),
('DEV4', 'Lobby', -80.1, 94.2, 52.8, '2026-04-19 11:00:00'),
('DEV5', 'Pharmacy', -69.4, 98.6, 43.9, '2026-04-19 11:00:00');


-- Inspection query: residents grouped by community.
SELECT
    c.name AS community,
    COUNT(r.id) AS resident_count
FROM communities c
LEFT JOIN residents r ON r.community_id = c.id
GROUP BY c.name
ORDER BY c.name;


-- Inspection query: list active document chunks with a short content preview.
SELECT
    id,
    source_title,
    source_path,
    chunk_index,
    LEFT(content, 300) AS preview,
    embedding_model,
    is_active
FROM documents
WHERE is_active = TRUE
ORDER BY source_path, chunk_index;


-- Inspection query: count active chunks per source document.
SELECT
    source_path,
    COUNT(*) AS active_chunks
FROM documents
WHERE is_active = TRUE
GROUP BY source_path
ORDER BY source_path;


-- Inspection query: view chunks from one source document.
-- Change source_path to inspect another file.
SELECT
    chunk_index,
    chunk_hash,
    LEFT(content, 500) AS preview
FROM documents
WHERE is_active = TRUE
  AND source_path = 'data/docs/device_alerts_and_troubleshooting.md'
ORDER BY chunk_index;


-- Similarity inspection query.
-- Picks one target chunk, compares all other active chunks to it, and ranks by vector distance.
-- Smaller distance means more similar. The target chunk itself is excluded.
WITH target AS ( 
    SELECT id, embedding
    FROM documents
    WHERE content ILIKE '%Healthcare IoT Monitoring Operations Guide%'
      AND is_active = TRUE
    LIMIT 1
)
SELECT
    d.id,
    d.source_title,
    d.source_path,
    d.chunk_index,
    d.embedding <-> target.embedding AS distance,
    LEFT(d.content, 250) AS preview
FROM documents d, target
WHERE d.is_active = TRUE
  AND d.id <> target.id
ORDER BY distance
LIMIT 5;
