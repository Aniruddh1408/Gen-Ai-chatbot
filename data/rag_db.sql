-- Enable pgvector so PostgreSQL can store and compare embedding vectors.
-- Required for the documents.embedding VECTOR(1024) column and <-> similarity search.
CREATE EXTENSION IF NOT EXISTS vector;


-- Core resident profile table.
-- This is the source of truth for resident demographics and static profile fields.
CREATE TABLE residents (
    id INTEGER PRIMARY KEY,
    name TEXT,
    flat_no TEXT,
    age INTEGER,
    health_medical_history TEXT,
    medical_intake_prescribed TEXT
);


-- Clinical health readings linked to a resident.
-- Each row represents one recorded blood pressure and sugar/glucose snapshot.
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


-- Speeds up RAG filtering for active chunks from the current embedding model.
CREATE INDEX documents_active_model_idx ON documents (is_active, embedding_model);

-- Speeds up source-level maintenance, inspection, and deactivation.
CREATE INDEX documents_source_idx ON documents (source_id, is_active);


-- Seed resident profile data for local development and testing.
INSERT INTO residents (id, name, flat_no, age, health_medical_history, medical_intake_prescribed) VALUES
(1, 'John Mathew', 'A-101', 78, 'Hypertension, Type 2 Diabetes', 'Metformin, Amlodipine'),
(2, 'Mary Dsouza', 'A-102', 82, 'Arthritis, Mild Asthma', 'Paracetamol, Salbutamol'),
(3, 'Ravi Kumar', 'B-201', 74, 'Cardiovascular disease', 'Atorvastatin, Aspirin'),
(4, 'Jason Murphy', 'B-202', 80, 'Osteoporosis', 'Calcium, Vitamin D'),
(5, 'Anil Sharma', 'C-301', 69, 'Pre-diabetes, Hypertension', 'Telmisartan');


-- Seed health readings.
-- These rows support SQL questions about BP and sugar/glucose values.
INSERT INTO health_reports (resident_id, bp_systolic, bp_diastolic, sugar_level, recorded_at) VALUES
(1, 148, 92, 182.5, '2026-04-18 08:30:00'),
(2, 132, 84, 118.0, '2026-04-18 09:00:00'),
(3, 156, 96, 140.2, '2026-04-18 09:30:00'),
(4, 128, 80, 108.4, '2026-04-18 10:00:00'),
(5, 142, 90, 165.1, '2026-04-18 10:30:00');


-- Seed activity readings.
-- These rows support SQL questions about steps and activity ranking.
INSERT INTO activity_metrics (resident_id, steps_count, recorded_at) VALUES
(1, 3200, '2026-04-18 20:00:00'),
(2, 4100, '2026-04-18 20:00:00'),
(3, 2500, '2026-04-18 20:00:00'),
(4, 5300, '2026-04-18 20:00:00'),
(5, 2900, '2026-04-18 20:00:00');


-- Seed sleep readings.
-- These rows support SQL questions about sleep duration and sleep quality rankings.
INSERT INTO sleep_analytics (resident_id, sleep_duration_minutes, sleep_quality_score, recorded_at) VALUES
(1, 360, 58, '2026-04-19 06:30:00'),
(2, 420, 74, '2026-04-19 06:30:00'),
(3, 310, 49, '2026-04-19 06:30:00'),
(4, 455, 81, '2026-04-19 06:30:00'),
(5, 340, 55, '2026-04-19 06:30:00');


-- Seed device telemetry.
-- These rows support SQL questions about device status, signal, uptime, CPU, and location.
INSERT INTO device_status (board_id, location, signal, uptime, cpu, time) VALUES
('DEV1', 'Ward A', -67.5, 99.1, 41.2, '2026-04-19 11:00:00'),
('DEV2', 'Ward B', -72.0, 97.8, 46.5, '2026-04-19 11:00:00'),
('DEV3', 'ICU', -61.3, 99.7, 38.4, '2026-04-19 11:00:00'),
('DEV4', 'Lobby', -80.1, 94.2, 52.8, '2026-04-19 11:00:00'),
('DEV5', 'Pharmacy', -69.4, 98.6, 43.9, '2026-04-19 11:00:00');



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
