-- Migration: enlarge columns for multi-object (head) detection
-- Reason: JSON arrays for confidence/label exceed original VARCHAR length causing Data truncation.
-- Safe to run multiple times if you first check existing data types.

-- 1. Inspect current schema
-- MySQL:
--   SHOW CREATE TABLE imgrecords;  -- verify current types
--   DESCRIBE imgrecords;           -- check column lengths

-- 2. Apply alterations (transactional)
START TRANSACTION;

-- Change to MEDIUMTEXT for future scalability (up to 16MB); TEXT (64KB) may also suffice.
ALTER TABLE imgrecords
  MODIFY COLUMN confidence MEDIUMTEXT NULL COMMENT 'JSON array or summary object of detection confidences',
  MODIFY COLUMN label MEDIUMTEXT NULL COMMENT 'JSON array of detection labels';

COMMIT;

-- 3. Optional rollback (only if previous type was VARCHAR(255))
-- START TRANSACTION;
-- ALTER TABLE imgrecords
--   MODIFY COLUMN confidence VARCHAR(255) NULL,
--   MODIFY COLUMN label VARCHAR(255) NULL;
-- COMMIT;

-- 4. Post-migration verification
--   INSERT INTO imgrecords (weight,input_img,out_img,confidence,all_time,conf,label,username,kind,start_time)
--   VALUES ('test.pt','in','out','[0.99,0.88,0.77,0.66,0.55,0.44,0.33,0.22,0.11]','0.123s','0.5','["head","head"]','tester','head','2025-11-18 12:00:00');
--   SELECT id, LENGTH(confidence) AS conf_len, LENGTH(label) AS label_len FROM imgrecords ORDER BY id DESC LIMIT 1;

-- 5. If using Spring Boot + MyBatis only (no Flyway), run this manually:
--   mysql -u <user> -p <database> < alter_imgrecords_columns.sql
-- Or paste commands inside a MySQL client.

-- 6. If you later decide to store summaries instead of full arrays, adjust application code before reverting type.
