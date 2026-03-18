-- Student behavior project schema optimization (item 9)
-- Target: MySQL 8.0+
-- Scope:
-- 1) Convert start_time from VARCHAR to DATETIME
-- 2) Convert conf from VARCHAR to DECIMAL(6,4)
-- 3) Add practical composite indexes for record queries
-- 4) Repair user table engine/constraints (InnoDB + unique username)
--
-- Execute with:
--   mysql -u <user> -p <database> < optimize_student_behavior_schema.sql

SET @OLD_FOREIGN_KEY_CHECKS = @@FOREIGN_KEY_CHECKS;
SET FOREIGN_KEY_CHECKS = 0;

-- ---------- 0) Data hygiene before type conversion ----------
-- Ensure username can safely become NOT NULL + UNIQUE.
UPDATE `user`
SET `username` = CONCAT('user_', `id`)
WHERE `username` IS NULL OR TRIM(`username`) = '';

-- Resolve duplicate usernames deterministically by suffixing id.
UPDATE `user` u
JOIN (
  SELECT `username`, MIN(`id`) AS keep_id
  FROM `user`
  GROUP BY `username`
  HAVING COUNT(*) > 1
) d
  ON u.`username` = d.`username` AND u.`id` <> d.keep_id
SET u.`username` = CONCAT(u.`username`, '_', u.`id`);

-- Clean invalid/empty timestamps and confidence values.
UPDATE `imgrecords`
SET `start_time` = NULL
WHERE `start_time` IS NOT NULL
  AND (TRIM(`start_time`) = '' OR STR_TO_DATE(`start_time`, '%Y-%m-%d %H:%i:%s') IS NULL);

UPDATE `videorecords`
SET `start_time` = NULL
WHERE `start_time` IS NOT NULL
  AND (TRIM(`start_time`) = '' OR STR_TO_DATE(`start_time`, '%Y-%m-%d %H:%i:%s') IS NULL);

UPDATE `camerarecords`
SET `start_time` = NULL
WHERE `start_time` IS NOT NULL
  AND (TRIM(`start_time`) = '' OR STR_TO_DATE(`start_time`, '%Y-%m-%d %H:%i:%s') IS NULL);

UPDATE `imgrecords`
SET `conf` = NULL
WHERE `conf` IS NOT NULL
  AND (TRIM(`conf`) = '' OR TRIM(`conf`) NOT REGEXP '^[0-9]+(\\.[0-9]+)?$');

UPDATE `videorecords`
SET `conf` = NULL
WHERE `conf` IS NOT NULL
  AND (TRIM(`conf`) = '' OR TRIM(`conf`) NOT REGEXP '^[0-9]+(\\.[0-9]+)?$');

UPDATE `camerarecords`
SET `conf` = NULL
WHERE `conf` IS NOT NULL
  AND (TRIM(`conf`) = '' OR TRIM(`conf`) NOT REGEXP '^[0-9]+(\\.[0-9]+)?$');

-- ---------- 1) Column type optimization ----------
ALTER TABLE `imgrecords`
  MODIFY COLUMN `start_time` DATETIME NULL,
  MODIFY COLUMN `conf` DECIMAL(6,4) NULL;

ALTER TABLE `videorecords`
  MODIFY COLUMN `start_time` DATETIME NULL,
  MODIFY COLUMN `conf` DECIMAL(6,4) NULL;

ALTER TABLE `camerarecords`
  MODIFY COLUMN `start_time` DATETIME NULL,
  MODIFY COLUMN `conf` DECIMAL(6,4) NULL;

ALTER TABLE `user`
  ENGINE = InnoDB,
  MODIFY COLUMN `username` VARCHAR(255) NOT NULL;

-- ---------- 2) Idempotent index helpers ----------
DROP PROCEDURE IF EXISTS add_index_if_missing;
DROP PROCEDURE IF EXISTS add_unique_index_if_missing;

DELIMITER $$
CREATE PROCEDURE add_index_if_missing(
  IN t_name VARCHAR(64),
  IN i_name VARCHAR(64),
  IN i_cols VARCHAR(255)
)
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = t_name
      AND index_name = i_name
  ) THEN
    SET @ddl = CONCAT('ALTER TABLE `', t_name, '` ADD INDEX `', i_name, '` ', i_cols);
    PREPARE stmt FROM @ddl;
    EXECUTE stmt;
    DEALLOCATE PREPARE stmt;
  END IF;
END$$

CREATE PROCEDURE add_unique_index_if_missing(
  IN t_name VARCHAR(64),
  IN i_name VARCHAR(64),
  IN i_cols VARCHAR(255)
)
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = t_name
      AND index_name = i_name
  ) THEN
    SET @ddl = CONCAT('ALTER TABLE `', t_name, '` ADD UNIQUE INDEX `', i_name, '` ', i_cols);
    PREPARE stmt FROM @ddl;
    EXECUTE stmt;
    DEALLOCATE PREPARE stmt;
  END IF;
END$$
DELIMITER ;

-- ---------- 3) Query indexes ----------
CALL add_index_if_missing('imgrecords', 'idx_img_user_time', '(username, start_time)');
CALL add_index_if_missing('imgrecords', 'idx_img_kind_time', '(kind, start_time)');
CALL add_index_if_missing('imgrecords', 'idx_img_weight', '(weight)');

CALL add_index_if_missing('videorecords', 'idx_video_user_time', '(username, start_time)');
CALL add_index_if_missing('videorecords', 'idx_video_kind_time', '(kind, start_time)');
CALL add_index_if_missing('videorecords', 'idx_video_weight', '(weight)');

CALL add_index_if_missing('camerarecords', 'idx_camera_user_time', '(username, start_time)');
CALL add_index_if_missing('camerarecords', 'idx_camera_kind_time', '(kind, start_time)');
CALL add_index_if_missing('camerarecords', 'idx_camera_weight', '(weight)');

CALL add_index_if_missing('student_behavior_records', 'idx_sbr_record_time', '(record_time)');
CALL add_index_if_missing('student_behavior_records', 'idx_sbr_class_time', '(classroom_id, record_time)');

CALL add_unique_index_if_missing('user', 'uk_user_username', '(username)');

-- ---------- 4) Cleanup ----------
DROP PROCEDURE IF EXISTS add_index_if_missing;
DROP PROCEDURE IF EXISTS add_unique_index_if_missing;

SET FOREIGN_KEY_CHECKS = @OLD_FOREIGN_KEY_CHECKS;

