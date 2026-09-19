-- 智算视界 · 单文件安装与升级 · MySQL 8.0+
-- 宝塔：先备份当前库，在 phpMyAdmin 左侧选中 wiscomper_com，再点 SQL，粘贴本文件全部内容执行。
-- 使用当前选中的数据库，不创建数据库、不切换库名，不需要 CREATE DATABASE 权限。
-- 支持空库、原网站 18 表及后续版本升级，补齐至 30 表，保留账户、权限、额度和学习数据。
-- 执行完应显示 upgrade_status=OK，无需逐个执行 database/migrations 中的文件。
-- 不执行 DROP TABLE、TRUNCATE、DELETE，不关闭外键检查，可重复执行。
-- 命令行：mysql -u USER -p --default-character-set=utf8mb4 DATABASE_NAME < visdom_db.sql
-- 要求已选中数据库。原库排序规则保持不变，新表默认兼容 utf8mb4_general_ci。
SET NAMES utf8mb4;
SET time_zone = '+00:00';
SET @wisdom_username_collation = COALESCE((SELECT COLLATION_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='users' AND COLUMN_NAME='username'), 'utf8mb4_general_ci');

-- 1. 账户与偏好
-- users
CREATE TABLE IF NOT EXISTS `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(255) NOT NULL,
  `hashed_password` varchar(255) NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- user_settings
CREATE TABLE IF NOT EXISTS `user_settings` (
  `user_id` varchar(64) NOT NULL,
  `settings_json` text,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- user_profiles
SET @wisdom_create = REPLACE('
CREATE TABLE IF NOT EXISTS `user_profiles` (
  `user_id` varchar(255) CHARACTER SET utf8mb4 COLLATE WISDOM_USERNAME_COLLATION NOT NULL,
  `avatar_url` varchar(512) DEFAULT NULL,
  `nickname` varchar(128) DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`),
  CONSTRAINT `fk_user_profiles_username` FOREIGN KEY (`user_id`) REFERENCES `users` (`username`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci', 'WISDOM_USERNAME_COLLATION', @wisdom_username_collation);
PREPARE wisdom_create_statement FROM @wisdom_create;
EXECUTE wisdom_create_statement;
DEALLOCATE PREPARE wisdom_create_statement;

-- 账户权限、试用额度与管理员操作记录
CREATE TABLE IF NOT EXISTS account_access (
    user_id INT PRIMARY KEY,
    role ENUM('member','vip','admin') NOT NULL DEFAULT 'member',
    disabled BOOLEAN NOT NULL DEFAULT FALSE,
    daily_limit INT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_access_user FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS access_settings (
    id TINYINT PRIMARY KEY,
    daily_limit INT NOT NULL DEFAULT 40,
    contact_email VARCHAR(254) NOT NULL DEFAULT 'rainbowyu619@gmail.com',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT IGNORE INTO access_settings(id) VALUES(1);

CREATE TABLE IF NOT EXISTS access_usage (
    principal VARCHAR(80) NOT NULL,
    period VARCHAR(10) NOT NULL,
    feature VARCHAR(20) NOT NULL,
    used INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY(principal,period,feature)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS access_audit (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    actor_id INT NOT NULL,
    target_id INT NULL,
    action VARCHAR(40) NOT NULL,
    details JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_access_audit_created(created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- 2. 算式、完整题解、脚本、智能体模板与成就
-- formulas
SET @wisdom_create = REPLACE('
CREATE TABLE IF NOT EXISTS `formulas` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` varchar(255) CHARACTER SET utf8mb4 COLLATE WISDOM_USERNAME_COLLATION NOT NULL,
  `latex` text NOT NULL,
  `note` varchar(255) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_formulas_owner_created` (`user_id`,`created_at`,`id`),
  CONSTRAINT `fk_formulas_username` FOREIGN KEY (`user_id`) REFERENCES `users` (`username`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci', 'WISDOM_USERNAME_COLLATION', @wisdom_username_collation);
PREPARE wisdom_create_statement FROM @wisdom_create;
EXECUTE wisdom_create_statement;
DEALLOCATE PREPARE wisdom_create_statement;

-- formula_topics
CREATE TABLE IF NOT EXISTS `formula_topics` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` varchar(64) NOT NULL,
  `formula_id` int NOT NULL,
  `tag` varchar(64) NOT NULL,
  `weight` float DEFAULT '1',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_user_tag` (`user_id`,`tag`),
  KEY `idx_formula` (`formula_id`),
  CONSTRAINT `fk_topic_formula` FOREIGN KEY (`formula_id`) REFERENCES `formulas` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- formula_solutions
CREATE TABLE IF NOT EXISTS `formula_solutions` (
  `formula_id` int NOT NULL,
  `title` varchar(240) NOT NULL,
  `step_count` int NOT NULL,
  `video_url` varchar(128) DEFAULT NULL,
  `payload` longtext NOT NULL,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`formula_id`),
  CONSTRAINT `fk_solution_formula` FOREIGN KEY (`formula_id`) REFERENCES `formulas` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- animation_scripts
SET @wisdom_create = REPLACE('
CREATE TABLE IF NOT EXISTS `animation_scripts` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` varchar(255) CHARACTER SET utf8mb4 COLLATE WISDOM_USERNAME_COLLATION NOT NULL,
  `note` varchar(255) DEFAULT '''',
  `code` mediumtext NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_scripts_owner_created` (`user_id`,`created_at`,`id`),
  CONSTRAINT `fk_animation_scripts_username` FOREIGN KEY (`user_id`) REFERENCES `users` (`username`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci', 'WISDOM_USERNAME_COLLATION', @wisdom_username_collation);
PREPARE wisdom_create_statement FROM @wisdom_create;
EXECUTE wisdom_create_statement;
DEALLOCATE PREPARE wisdom_create_statement;

-- agent_templates
SET @wisdom_create = REPLACE('
CREATE TABLE IF NOT EXISTS `agent_templates` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` varchar(255) CHARACTER SET utf8mb4 COLLATE WISDOM_USERNAME_COLLATION NOT NULL,
  `name` varchar(256) NOT NULL DEFAULT ''未命名'',
  `prompt` text NOT NULL,
  `steps_json` mediumtext,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_templates_owner_created` (`user_id`,`created_at`,`id`),
  CONSTRAINT `fk_agent_templates_username` FOREIGN KEY (`user_id`) REFERENCES `users` (`username`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci', 'WISDOM_USERNAME_COLLATION', @wisdom_username_collation);
PREPARE wisdom_create_statement FROM @wisdom_create;
EXECUTE wisdom_create_statement;
DEALLOCATE PREPARE wisdom_create_statement;

-- user_achievements
CREATE TABLE IF NOT EXISTS `user_achievements` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` varchar(255) NOT NULL,
  `achievement_id` varchar(64) NOT NULL,
  `progress` int NOT NULL DEFAULT '0',
  `unlocked` tinyint(1) NOT NULL DEFAULT '0',
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_user_ach` (`user_id`,`achievement_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- 3. 课包、教案与课堂视频
-- course_packs
CREATE TABLE IF NOT EXISTS `course_packs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` varchar(64) NOT NULL,
  `name` varchar(128) NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_packs_owner_created` (`user_id`,`created_at`,`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- course_pack_documents
CREATE TABLE IF NOT EXISTS `course_pack_documents` (
  `pack_id` int NOT NULL,
  `description` text NOT NULL,
  `lesson_json` longtext NOT NULL,
  `revision` int NOT NULL DEFAULT '1',
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`pack_id`),
  CONSTRAINT `fk_pack_document` FOREIGN KEY (`pack_id`) REFERENCES `course_packs` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- course_pack_videos
CREATE TABLE IF NOT EXISTS `course_pack_videos` (
  `pack_id` int NOT NULL,
  `video_id` varchar(128) NOT NULL,
  `sort_order` int DEFAULT '0',
  PRIMARY KEY (`pack_id`,`video_id`),
  KEY `ix_pack_order` (`pack_id`,`sort_order`),
  CONSTRAINT `fk_pack_video` FOREIGN KEY (`pack_id`) REFERENCES `course_packs` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- 4. 视频互动、观看进度、收藏与笔记
-- example_video_likes
CREATE TABLE IF NOT EXISTS `example_video_likes` (
  `video_id` varchar(128) NOT NULL,
  `user_id` varchar(64) NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`video_id`,`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- example_video_comments
CREATE TABLE IF NOT EXISTS `example_video_comments` (
  `id` int NOT NULL AUTO_INCREMENT,
  `video_id` varchar(128) NOT NULL,
  `user_id` varchar(64) NOT NULL,
  `content` text NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_comments_video_created` (`video_id`,`created_at`,`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- example_video_danmaku
CREATE TABLE IF NOT EXISTS `example_video_danmaku` (
  `id` int NOT NULL AUTO_INCREMENT,
  `video_id` varchar(128) NOT NULL,
  `user_id` varchar(64) NOT NULL,
  `text` varchar(80) NOT NULL,
  `time` double NOT NULL,
  `color` int DEFAULT '16777215',
  `mode` smallint DEFAULT '1',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_danmaku_video_time` (`video_id`,`time`,`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- example_play_history
CREATE TABLE IF NOT EXISTS `example_play_history` (
  `user_id` varchar(64) NOT NULL,
  `video_id` varchar(128) NOT NULL,
  `progress` double NOT NULL DEFAULT '0',
  `last_active` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`,`video_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- example_video_notes
CREATE TABLE IF NOT EXISTS `example_video_notes` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` varchar(64) NOT NULL,
  `video_id` varchar(128) NOT NULL,
  `time_sec` double NOT NULL DEFAULT '0',
  `content` text NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_notes_owner_video_time` (`user_id`,`video_id`,`time_sec`,`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- user_favorites
CREATE TABLE IF NOT EXISTS `user_favorites` (
  `user_id` varchar(64) NOT NULL,
  `video_id` varchar(128) NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`,`video_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- watch_later
CREATE TABLE IF NOT EXISTS `watch_later` (
  `user_id` varchar(64) NOT NULL,
  `video_id` varchar(128) NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`,`video_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- 5. 错题归档、学习记录与复习计划
-- user_wrongbook
CREATE TABLE IF NOT EXISTS `user_wrongbook` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` varchar(255) NOT NULL,
  `video_id` varchar(256) NOT NULL,
  `title` varchar(512) DEFAULT '',
  `time_sec` int NOT NULL DEFAULT '0',
  `note` text,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- learning_wrongbook
CREATE TABLE IF NOT EXISTS `learning_wrongbook` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `owner_id` int NOT NULL,
  `legacy_id` int DEFAULT NULL,
  `source_type` enum('manual','video','solution') NOT NULL DEFAULT 'manual',
  `video_id` varchar(256) NOT NULL DEFAULT '',
  `formula_id` int DEFAULT NULL,
  `time_sec` int unsigned NOT NULL DEFAULT '0',
  `title` varchar(512) NOT NULL,
  `problem` text NOT NULL,
  `answer` mediumtext NOT NULL,
  `note` text NOT NULL,
  `solution_snapshot` json DEFAULT NULL,
  `fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `status` enum('new','reviewing','mastered') NOT NULL DEFAULT 'new',
  `difficulty` tinyint unsigned NOT NULL DEFAULT '3',
  `review_count` int unsigned NOT NULL DEFAULT '0',
  `interval_days` int unsigned NOT NULL DEFAULT '0',
  `next_review_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `last_reviewed_at` datetime DEFAULT NULL,
  `revision` int unsigned NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_wrongbook_origin` (`owner_id`,`fingerprint`),
  UNIQUE KEY `uq_wrongbook_legacy` (`legacy_id`),
  KEY `ix_wrongbook_due` (`owner_id`,`status`,`next_review_at`,`id`),
  KEY `ix_wrongbook_recent` (`owner_id`,`updated_at`,`id`),
  KEY `ix_wrongbook_video` (`owner_id`,`video_id`,`time_sec`),
  KEY `fk_wrongbook_formula` (`formula_id`),
  CONSTRAINT `fk_wrongbook_formula` FOREIGN KEY (`formula_id`) REFERENCES `formulas` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_wrongbook_owner` FOREIGN KEY (`owner_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `ck_wrongbook_difficulty` CHECK ((`difficulty` between 1 and 5))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- learning_wrongbook_tags
CREATE TABLE IF NOT EXISTS `learning_wrongbook_tags` (
  `entry_id` bigint unsigned NOT NULL,
  `tag` varchar(64) NOT NULL,
  PRIMARY KEY (`entry_id`,`tag`),
  KEY `ix_wrongbook_tag` (`tag`,`entry_id`),
  CONSTRAINT `fk_wrongbook_tag_entry` FOREIGN KEY (`entry_id`) REFERENCES `learning_wrongbook` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- learning_wrongbook_reviews
CREATE TABLE IF NOT EXISTS `learning_wrongbook_reviews` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `entry_id` bigint unsigned NOT NULL,
  `grade` enum('again','good','mastered') NOT NULL,
  `note` text NOT NULL,
  `interval_days` int unsigned NOT NULL,
  `next_review_at` datetime DEFAULT NULL,
  `reviewed_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_wrongbook_review` (`entry_id`,`reviewed_at`,`id`),
  CONSTRAINT `fk_wrongbook_review_entry` FOREIGN KEY (`entry_id`) REFERENCES `learning_wrongbook` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- 6. 跨模块学习材料（依赖课包、算式与错题表）
-- course_pack_resources：有序学习材料，来源删除时保留内容快照。
CREATE TABLE IF NOT EXISTS course_pack_resources (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    pack_id INT NOT NULL,
    kind ENUM('solution','wrongbook') NOT NULL,
    formula_id INT NULL,
    wrongbook_id BIGINT UNSIGNED NULL,
    snapshot JSON NOT NULL,
    sort_order INT UNSIGNED NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY ix_pack_resource_order(pack_id,sort_order,id),
    UNIQUE KEY uq_pack_formula(pack_id,formula_id),
    UNIQUE KEY uq_pack_wrongbook(pack_id,wrongbook_id),
    CONSTRAINT fk_resource_pack FOREIGN KEY(pack_id) REFERENCES course_packs(id) ON DELETE CASCADE,
    CONSTRAINT fk_resource_formula FOREIGN KEY(formula_id) REFERENCES formulas(id) ON DELETE SET NULL,
    CONSTRAINT fk_resource_wrongbook FOREIGN KEY(wrongbook_id) REFERENCES learning_wrongbook(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- 请求管理记录：仅主账号可读取，保留 90 天。
CREATE TABLE IF NOT EXISTS request_records (
    id CHAR(32) PRIMARY KEY,
    owner_id INT NULL,
    username VARCHAR(64) NOT NULL DEFAULT '',
    role VARCHAR(16) NOT NULL DEFAULT 'guest',
    feature VARCHAR(24) NOT NULL,
    endpoint VARCHAR(100) NOT NULL,
    problem MEDIUMTEXT NOT NULL,
    has_image BOOLEAN NOT NULL DEFAULT FALSE,
    content_truncated BOOLEAN NOT NULL DEFAULT FALSE,
    device VARCHAR(40) NOT NULL DEFAULT '',
    status VARCHAR(24) NOT NULL DEFAULT 'processing',
    http_status SMALLINT NULL,
    duration_ms INT UNSIGNED NULL,
    job_id CHAR(32) NULL,
    created_at DATETIME(3) NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX ix_requests_time(created_at,id),
    INDEX ix_requests_owner_time(owner_id,created_at,id),
    INDEX ix_requests_status_time(status,created_at,id),
    INDEX ix_requests_feature_time(feature,created_at,id),
    INDEX ix_requests_job(job_id),
    CONSTRAINT fk_request_owner FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- 7. 应用升级记录（完成校验后同步版本，保留已有校验和）
-- schema_migrations
CREATE TABLE IF NOT EXISTS `schema_migrations` (
  `version` varchar(128) NOT NULL,
  `checksum` char(64) NOT NULL,
  `applied_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- 8. 可重复执行的旧库升级

-- 使用普通 SQL 和会话级 PREPARE，不需要 SOURCE、DELIMITER 或存储过程权限。

-- 如有不合法的旧关联，添加外键会报错并保留数据，请修正归属后重试。

SET @wisdom_ddl = IF(EXISTS(SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='example_video_danmaku' AND COLUMN_NAME='color'), 'DO 0', 'ALTER TABLE `example_video_danmaku` ADD COLUMN `color` INT DEFAULT 16777215 AFTER `time`');

PREPARE wisdom_statement FROM @wisdom_ddl;

EXECUTE wisdom_statement;

DEALLOCATE PREPARE wisdom_statement;

SET @wisdom_ddl = IF(EXISTS(SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='example_video_danmaku' AND COLUMN_NAME='mode'), 'DO 0', 'ALTER TABLE `example_video_danmaku` ADD COLUMN `mode` SMALLINT DEFAULT 1 AFTER `color`');

PREPARE wisdom_statement FROM @wisdom_ddl;

EXECUTE wisdom_statement;

DEALLOCATE PREPARE wisdom_statement;

SET @wisdom_ddl = IF(EXISTS(SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='example_video_danmaku' AND INDEX_NAME='ix_danmaku_video_time'), 'DO 0', 'ALTER TABLE `example_video_danmaku` ADD INDEX `ix_danmaku_video_time` (video_id,time,id)');

PREPARE wisdom_statement FROM @wisdom_ddl;

EXECUTE wisdom_statement;

DEALLOCATE PREPARE wisdom_statement;

SET @wisdom_ddl = IF(EXISTS(SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='example_video_comments' AND INDEX_NAME='ix_comments_video_created'), 'DO 0', 'ALTER TABLE `example_video_comments` ADD INDEX `ix_comments_video_created` (video_id,created_at,id)');

PREPARE wisdom_statement FROM @wisdom_ddl;

EXECUTE wisdom_statement;

DEALLOCATE PREPARE wisdom_statement;

SET @wisdom_ddl = IF(EXISTS(SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='example_video_notes' AND INDEX_NAME='ix_notes_owner_video_time'), 'DO 0', 'ALTER TABLE `example_video_notes` ADD INDEX `ix_notes_owner_video_time` (user_id,video_id,time_sec,id)');

PREPARE wisdom_statement FROM @wisdom_ddl;

EXECUTE wisdom_statement;

DEALLOCATE PREPARE wisdom_statement;

SET @wisdom_ddl = IF(EXISTS(SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='course_packs' AND INDEX_NAME='ix_packs_owner_created'), 'DO 0', 'ALTER TABLE `course_packs` ADD INDEX `ix_packs_owner_created` (user_id,created_at,id)');

PREPARE wisdom_statement FROM @wisdom_ddl;

EXECUTE wisdom_statement;

DEALLOCATE PREPARE wisdom_statement;

SET @wisdom_ddl = IF(EXISTS(SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='course_pack_videos' AND INDEX_NAME='ix_pack_order'), 'DO 0', 'ALTER TABLE `course_pack_videos` ADD INDEX `ix_pack_order` (pack_id,sort_order)');

PREPARE wisdom_statement FROM @wisdom_ddl;

EXECUTE wisdom_statement;

DEALLOCATE PREPARE wisdom_statement;

SET @wisdom_ddl = IF(EXISTS(SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='formulas' AND INDEX_NAME='ix_formulas_owner_created'), 'DO 0', 'ALTER TABLE `formulas` ADD INDEX `ix_formulas_owner_created` (user_id,created_at,id)');

PREPARE wisdom_statement FROM @wisdom_ddl;

EXECUTE wisdom_statement;

DEALLOCATE PREPARE wisdom_statement;

SET @wisdom_ddl = IF(EXISTS(SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='animation_scripts' AND INDEX_NAME='ix_scripts_owner_created'), 'DO 0', 'ALTER TABLE `animation_scripts` ADD INDEX `ix_scripts_owner_created` (user_id,created_at,id)');

PREPARE wisdom_statement FROM @wisdom_ddl;

EXECUTE wisdom_statement;

DEALLOCATE PREPARE wisdom_statement;

SET @wisdom_ddl = IF(EXISTS(SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='agent_templates' AND INDEX_NAME='ix_templates_owner_created'), 'DO 0', 'ALTER TABLE `agent_templates` ADD INDEX `ix_templates_owner_created` (user_id,created_at,id)');

PREPARE wisdom_statement FROM @wisdom_ddl;

EXECUTE wisdom_statement;

DEALLOCATE PREPARE wisdom_statement;

SET @wisdom_fk = NULL;
SET @wisdom_fk_update = NULL;
SELECT rc.CONSTRAINT_NAME, rc.UPDATE_RULE INTO @wisdom_fk, @wisdom_fk_update
FROM information_schema.REFERENTIAL_CONSTRAINTS rc
JOIN information_schema.KEY_COLUMN_USAGE k
  ON rc.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA AND rc.TABLE_NAME=k.TABLE_NAME AND rc.CONSTRAINT_NAME=k.CONSTRAINT_NAME
WHERE rc.CONSTRAINT_SCHEMA=DATABASE() AND rc.TABLE_NAME='formulas'
  AND k.COLUMN_NAME='user_id' AND k.REFERENCED_TABLE_NAME='users' AND k.REFERENCED_COLUMN_NAME='username'
LIMIT 1;

SET @wisdom_ddl = IF(@wisdom_fk_update='CASCADE', 'DO 0', CONCAT('ALTER TABLE `formulas` ', IF(@wisdom_fk IS NULL, '', CONCAT('DROP FOREIGN KEY `', REPLACE(@wisdom_fk, '`', '``'), '`, ')), 'ADD CONSTRAINT fk_formulas_username FOREIGN KEY(user_id) REFERENCES users(username) ON DELETE CASCADE ON UPDATE CASCADE'));

PREPARE wisdom_statement FROM @wisdom_ddl;

EXECUTE wisdom_statement;

DEALLOCATE PREPARE wisdom_statement;

SET @wisdom_fk = NULL;
SET @wisdom_fk_update = NULL;
SELECT rc.CONSTRAINT_NAME, rc.UPDATE_RULE INTO @wisdom_fk, @wisdom_fk_update
FROM information_schema.REFERENTIAL_CONSTRAINTS rc
JOIN information_schema.KEY_COLUMN_USAGE k
  ON rc.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA AND rc.TABLE_NAME=k.TABLE_NAME AND rc.CONSTRAINT_NAME=k.CONSTRAINT_NAME
WHERE rc.CONSTRAINT_SCHEMA=DATABASE() AND rc.TABLE_NAME='animation_scripts'
  AND k.COLUMN_NAME='user_id' AND k.REFERENCED_TABLE_NAME='users' AND k.REFERENCED_COLUMN_NAME='username'
LIMIT 1;

SET @wisdom_ddl = IF(@wisdom_fk_update='CASCADE', 'DO 0', CONCAT('ALTER TABLE `animation_scripts` ', IF(@wisdom_fk IS NULL, '', CONCAT('DROP FOREIGN KEY `', REPLACE(@wisdom_fk, '`', '``'), '`, ')), 'ADD CONSTRAINT fk_animation_scripts_username FOREIGN KEY(user_id) REFERENCES users(username) ON DELETE CASCADE ON UPDATE CASCADE'));

PREPARE wisdom_statement FROM @wisdom_ddl;

EXECUTE wisdom_statement;

DEALLOCATE PREPARE wisdom_statement;

SET @wisdom_fk = NULL;
SET @wisdom_fk_update = NULL;
SELECT rc.CONSTRAINT_NAME, rc.UPDATE_RULE INTO @wisdom_fk, @wisdom_fk_update
FROM information_schema.REFERENTIAL_CONSTRAINTS rc
JOIN information_schema.KEY_COLUMN_USAGE k
  ON rc.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA AND rc.TABLE_NAME=k.TABLE_NAME AND rc.CONSTRAINT_NAME=k.CONSTRAINT_NAME
WHERE rc.CONSTRAINT_SCHEMA=DATABASE() AND rc.TABLE_NAME='agent_templates'
  AND k.COLUMN_NAME='user_id' AND k.REFERENCED_TABLE_NAME='users' AND k.REFERENCED_COLUMN_NAME='username'
LIMIT 1;

SET @wisdom_ddl = IF(@wisdom_fk_update='CASCADE', 'DO 0', CONCAT('ALTER TABLE `agent_templates` ', IF(@wisdom_fk IS NULL, '', CONCAT('DROP FOREIGN KEY `', REPLACE(@wisdom_fk, '`', '``'), '`, ')), 'ADD CONSTRAINT fk_agent_templates_username FOREIGN KEY(user_id) REFERENCES users(username) ON DELETE CASCADE ON UPDATE CASCADE'));

PREPARE wisdom_statement FROM @wisdom_ddl;

EXECUTE wisdom_statement;

DEALLOCATE PREPARE wisdom_statement;

SET @wisdom_fk = NULL;
SET @wisdom_fk_update = NULL;
SELECT rc.CONSTRAINT_NAME, rc.UPDATE_RULE INTO @wisdom_fk, @wisdom_fk_update
FROM information_schema.REFERENTIAL_CONSTRAINTS rc
JOIN information_schema.KEY_COLUMN_USAGE k
  ON rc.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA AND rc.TABLE_NAME=k.TABLE_NAME AND rc.CONSTRAINT_NAME=k.CONSTRAINT_NAME
WHERE rc.CONSTRAINT_SCHEMA=DATABASE() AND rc.TABLE_NAME='user_profiles'
  AND k.COLUMN_NAME='user_id' AND k.REFERENCED_TABLE_NAME='users' AND k.REFERENCED_COLUMN_NAME='username'
LIMIT 1;

SET @wisdom_ddl = IF(@wisdom_fk_update='CASCADE', 'DO 0', CONCAT('ALTER TABLE `user_profiles` ', IF(@wisdom_fk IS NULL, '', CONCAT('DROP FOREIGN KEY `', REPLACE(@wisdom_fk, '`', '``'), '`, ')), 'ADD CONSTRAINT fk_user_profiles_username FOREIGN KEY(user_id) REFERENCES users(username) ON DELETE CASCADE ON UPDATE CASCADE'));

PREPARE wisdom_statement FROM @wisdom_ddl;

EXECUTE wisdom_statement;

DEALLOCATE PREPARE wisdom_statement;

SET @wisdom_ddl = IF(EXISTS(SELECT 1 FROM information_schema.KEY_COLUMN_USAGE WHERE CONSTRAINT_SCHEMA=DATABASE() AND TABLE_NAME='course_pack_documents' AND COLUMN_NAME='pack_id' AND REFERENCED_TABLE_NAME='course_packs'), 'DO 0', 'ALTER TABLE `course_pack_documents` ADD CONSTRAINT `fk_pack_document` FOREIGN KEY(`pack_id`) REFERENCES `course_packs`(id) ON DELETE CASCADE');

PREPARE wisdom_statement FROM @wisdom_ddl;

EXECUTE wisdom_statement;

DEALLOCATE PREPARE wisdom_statement;

SET @wisdom_ddl = IF(EXISTS(SELECT 1 FROM information_schema.KEY_COLUMN_USAGE WHERE CONSTRAINT_SCHEMA=DATABASE() AND TABLE_NAME='course_pack_videos' AND COLUMN_NAME='pack_id' AND REFERENCED_TABLE_NAME='course_packs'), 'DO 0', 'ALTER TABLE `course_pack_videos` ADD CONSTRAINT `fk_pack_video` FOREIGN KEY(`pack_id`) REFERENCES `course_packs`(id) ON DELETE CASCADE');

PREPARE wisdom_statement FROM @wisdom_ddl;

EXECUTE wisdom_statement;

DEALLOCATE PREPARE wisdom_statement;

SET @wisdom_ddl = IF(EXISTS(SELECT 1 FROM information_schema.KEY_COLUMN_USAGE WHERE CONSTRAINT_SCHEMA=DATABASE() AND TABLE_NAME='formula_topics' AND COLUMN_NAME='formula_id' AND REFERENCED_TABLE_NAME='formulas'), 'DO 0', 'ALTER TABLE `formula_topics` ADD CONSTRAINT `fk_topic_formula` FOREIGN KEY(`formula_id`) REFERENCES `formulas`(id) ON DELETE CASCADE');

PREPARE wisdom_statement FROM @wisdom_ddl;

EXECUTE wisdom_statement;

DEALLOCATE PREPARE wisdom_statement;

-- 保留原错题表，将可匹配账户的记录导入新错题本，重复执行不重复导入。
INSERT INTO learning_wrongbook
    (owner_id,legacy_id,source_type,video_id,time_sec,title,problem,answer,note,fingerprint,created_at)
SELECT u.id,w.id,'video',w.video_id,GREATEST(w.time_sec,0),
    COALESCE(w.title,''),COALESCE(w.title,''),'',COALESCE(w.note,''),
    SHA2(CONCAT('legacy:',w.id),256),COALESCE(w.created_at,CURRENT_TIMESTAMP)
FROM user_wrongbook w JOIN users u
    ON BINARY u.username = BINARY w.user_id
WHERE NOT EXISTS (SELECT 1 FROM learning_wrongbook n WHERE n.legacy_id=w.id);


-- 9. 结构自检与升级版本登记（由 scripts/build_database_installer.py 同步生成）
-- 缺少字段、索引、关联或历史校验和冲突时，不登记新版本，不覆盖已有记录。
SET @wisdom_schema = '[
{"table": "users", "columns": ["id", "username", "hashed_password", "created_at"], "indexes": [{"name": "PRIMARY", "columns": "id", "unique": 1}, {"name": "username", "columns": "username", "unique": 1}], "foreign_keys": []},
{"table": "user_settings", "columns": ["user_id", "settings_json", "updated_at"], "indexes": [{"name": "PRIMARY", "columns": "user_id", "unique": 1}], "foreign_keys": []},
{"table": "user_profiles", "columns": ["user_id", "avatar_url", "nickname", "updated_at"], "indexes": [{"name": "PRIMARY", "columns": "user_id", "unique": 1}], "foreign_keys": [{"column": "user_id", "parent": "users", "parent_column": "username", "delete_rule": "CASCADE", "update_cascade": 1}]},
{"table": "account_access", "columns": ["user_id", "role", "disabled", "daily_limit", "updated_at"], "indexes": [{"name": "PRIMARY", "columns": "user_id", "unique": 1}], "foreign_keys": [{"column": "user_id", "parent": "users", "parent_column": "id", "delete_rule": "CASCADE", "update_cascade": 0}]},
{"table": "access_settings", "columns": ["id", "daily_limit", "contact_email", "updated_at"], "indexes": [{"name": "PRIMARY", "columns": "id", "unique": 1}], "foreign_keys": []},
{"table": "access_usage", "columns": ["principal", "period", "feature", "used", "updated_at"], "indexes": [{"name": "PRIMARY", "columns": "principal,period,feature", "unique": 1}], "foreign_keys": []},
{"table": "access_audit", "columns": ["id", "actor_id", "target_id", "action", "details", "created_at"], "indexes": [{"name": "PRIMARY", "columns": "id", "unique": 1}, {"name": "ix_access_audit_created", "columns": "created_at", "unique": 0}], "foreign_keys": []},
{"table": "formulas", "columns": ["id", "user_id", "latex", "note", "created_at"], "indexes": [{"name": "PRIMARY", "columns": "id", "unique": 1}, {"name": "ix_formulas_owner_created", "columns": "user_id,created_at,id", "unique": 0}], "foreign_keys": [{"column": "user_id", "parent": "users", "parent_column": "username", "delete_rule": "CASCADE", "update_cascade": 1}]},
{"table": "formula_topics", "columns": ["id", "user_id", "formula_id", "tag", "weight", "created_at"], "indexes": [{"name": "PRIMARY", "columns": "id", "unique": 1}, {"name": "idx_user_tag", "columns": "user_id,tag", "unique": 0}, {"name": "idx_formula", "columns": "formula_id", "unique": 0}], "foreign_keys": [{"column": "formula_id", "parent": "formulas", "parent_column": "id", "delete_rule": "CASCADE", "update_cascade": 0}]},
{"table": "formula_solutions", "columns": ["formula_id", "title", "step_count", "video_url", "payload", "updated_at"], "indexes": [{"name": "PRIMARY", "columns": "formula_id", "unique": 1}], "foreign_keys": [{"column": "formula_id", "parent": "formulas", "parent_column": "id", "delete_rule": "CASCADE", "update_cascade": 0}]},
{"table": "animation_scripts", "columns": ["id", "user_id", "note", "code", "created_at"], "indexes": [{"name": "PRIMARY", "columns": "id", "unique": 1}, {"name": "ix_scripts_owner_created", "columns": "user_id,created_at,id", "unique": 0}], "foreign_keys": [{"column": "user_id", "parent": "users", "parent_column": "username", "delete_rule": "CASCADE", "update_cascade": 1}]},
{"table": "agent_templates", "columns": ["id", "user_id", "name", "prompt", "steps_json", "created_at"], "indexes": [{"name": "PRIMARY", "columns": "id", "unique": 1}, {"name": "ix_templates_owner_created", "columns": "user_id,created_at,id", "unique": 0}], "foreign_keys": [{"column": "user_id", "parent": "users", "parent_column": "username", "delete_rule": "CASCADE", "update_cascade": 1}]},
{"table": "user_achievements", "columns": ["id", "user_id", "achievement_id", "progress", "unlocked", "updated_at"], "indexes": [{"name": "PRIMARY", "columns": "id", "unique": 1}, {"name": "uq_user_ach", "columns": "user_id,achievement_id", "unique": 1}], "foreign_keys": []},
{"table": "course_packs", "columns": ["id", "user_id", "name", "created_at"], "indexes": [{"name": "PRIMARY", "columns": "id", "unique": 1}, {"name": "ix_packs_owner_created", "columns": "user_id,created_at,id", "unique": 0}], "foreign_keys": []},
{"table": "course_pack_documents", "columns": ["pack_id", "description", "lesson_json", "revision", "updated_at"], "indexes": [{"name": "PRIMARY", "columns": "pack_id", "unique": 1}], "foreign_keys": [{"column": "pack_id", "parent": "course_packs", "parent_column": "id", "delete_rule": "CASCADE", "update_cascade": 0}]},
{"table": "course_pack_videos", "columns": ["pack_id", "video_id", "sort_order"], "indexes": [{"name": "PRIMARY", "columns": "pack_id,video_id", "unique": 1}, {"name": "ix_pack_order", "columns": "pack_id,sort_order", "unique": 0}], "foreign_keys": [{"column": "pack_id", "parent": "course_packs", "parent_column": "id", "delete_rule": "CASCADE", "update_cascade": 0}]},
{"table": "example_video_likes", "columns": ["video_id", "user_id", "created_at"], "indexes": [{"name": "PRIMARY", "columns": "video_id,user_id", "unique": 1}], "foreign_keys": []},
{"table": "example_video_comments", "columns": ["id", "video_id", "user_id", "content", "created_at"], "indexes": [{"name": "PRIMARY", "columns": "id", "unique": 1}, {"name": "ix_comments_video_created", "columns": "video_id,created_at,id", "unique": 0}], "foreign_keys": []},
{"table": "example_video_danmaku", "columns": ["id", "video_id", "user_id", "text", "time", "color", "mode", "created_at"], "indexes": [{"name": "PRIMARY", "columns": "id", "unique": 1}, {"name": "ix_danmaku_video_time", "columns": "video_id,time,id", "unique": 0}], "foreign_keys": []},
{"table": "example_play_history", "columns": ["user_id", "video_id", "progress", "last_active"], "indexes": [{"name": "PRIMARY", "columns": "user_id,video_id", "unique": 1}], "foreign_keys": []},
{"table": "example_video_notes", "columns": ["id", "user_id", "video_id", "time_sec", "content", "created_at"], "indexes": [{"name": "PRIMARY", "columns": "id", "unique": 1}, {"name": "ix_notes_owner_video_time", "columns": "user_id,video_id,time_sec,id", "unique": 0}], "foreign_keys": []},
{"table": "user_favorites", "columns": ["user_id", "video_id", "created_at"], "indexes": [{"name": "PRIMARY", "columns": "user_id,video_id", "unique": 1}], "foreign_keys": []},
{"table": "watch_later", "columns": ["user_id", "video_id", "created_at"], "indexes": [{"name": "PRIMARY", "columns": "user_id,video_id", "unique": 1}], "foreign_keys": []},
{"table": "user_wrongbook", "columns": ["id", "user_id", "video_id", "title", "time_sec", "note", "created_at"], "indexes": [{"name": "PRIMARY", "columns": "id", "unique": 1}], "foreign_keys": []},
{"table": "learning_wrongbook", "columns": ["id", "owner_id", "legacy_id", "source_type", "video_id", "formula_id", "time_sec", "title", "problem", "answer", "note", "solution_snapshot", "fingerprint", "status", "difficulty", "review_count", "interval_days", "next_review_at", "last_reviewed_at", "revision", "created_at", "updated_at"], "indexes": [{"name": "PRIMARY", "columns": "id", "unique": 1}, {"name": "uq_wrongbook_origin", "columns": "owner_id,fingerprint", "unique": 1}, {"name": "uq_wrongbook_legacy", "columns": "legacy_id", "unique": 1}, {"name": "ix_wrongbook_due", "columns": "owner_id,status,next_review_at,id", "unique": 0}, {"name": "ix_wrongbook_recent", "columns": "owner_id,updated_at,id", "unique": 0}, {"name": "ix_wrongbook_video", "columns": "owner_id,video_id,time_sec", "unique": 0}, {"name": "fk_wrongbook_formula", "columns": "formula_id", "unique": 0}], "foreign_keys": [{"column": "formula_id", "parent": "formulas", "parent_column": "id", "delete_rule": "SET NULL", "update_cascade": 0}, {"column": "owner_id", "parent": "users", "parent_column": "id", "delete_rule": "CASCADE", "update_cascade": 0}]},
{"table": "learning_wrongbook_tags", "columns": ["entry_id", "tag"], "indexes": [{"name": "PRIMARY", "columns": "entry_id,tag", "unique": 1}, {"name": "ix_wrongbook_tag", "columns": "tag,entry_id", "unique": 0}], "foreign_keys": [{"column": "entry_id", "parent": "learning_wrongbook", "parent_column": "id", "delete_rule": "CASCADE", "update_cascade": 0}]},
{"table": "learning_wrongbook_reviews", "columns": ["id", "entry_id", "grade", "note", "interval_days", "next_review_at", "reviewed_at"], "indexes": [{"name": "PRIMARY", "columns": "id", "unique": 1}, {"name": "ix_wrongbook_review", "columns": "entry_id,reviewed_at,id", "unique": 0}], "foreign_keys": [{"column": "entry_id", "parent": "learning_wrongbook", "parent_column": "id", "delete_rule": "CASCADE", "update_cascade": 0}]},
{"table": "course_pack_resources", "columns": ["id", "pack_id", "kind", "formula_id", "wrongbook_id", "snapshot", "sort_order", "created_at"], "indexes": [{"name": "PRIMARY", "columns": "id", "unique": 1}, {"name": "ix_pack_resource_order", "columns": "pack_id,sort_order,id", "unique": 0}, {"name": "uq_pack_formula", "columns": "pack_id,formula_id", "unique": 1}, {"name": "uq_pack_wrongbook", "columns": "pack_id,wrongbook_id", "unique": 1}], "foreign_keys": [{"column": "pack_id", "parent": "course_packs", "parent_column": "id", "delete_rule": "CASCADE", "update_cascade": 0}, {"column": "formula_id", "parent": "formulas", "parent_column": "id", "delete_rule": "SET NULL", "update_cascade": 0}, {"column": "wrongbook_id", "parent": "learning_wrongbook", "parent_column": "id", "delete_rule": "SET NULL", "update_cascade": 0}]},
{"table": "request_records", "columns": ["id", "owner_id", "username", "role", "feature", "endpoint", "problem", "has_image", "content_truncated", "device", "status", "http_status", "duration_ms", "job_id", "created_at", "updated_at"], "indexes": [{"name": "PRIMARY", "columns": "id", "unique": 1}, {"name": "ix_requests_time", "columns": "created_at,id", "unique": 0}, {"name": "ix_requests_owner_time", "columns": "owner_id,created_at,id", "unique": 0}, {"name": "ix_requests_status_time", "columns": "status,created_at,id", "unique": 0}, {"name": "ix_requests_feature_time", "columns": "feature,created_at,id", "unique": 0}, {"name": "ix_requests_job", "columns": "job_id", "unique": 0}], "foreign_keys": [{"column": "owner_id", "parent": "users", "parent_column": "id", "delete_rule": "SET NULL", "update_cascade": 0}]},
{"table": "schema_migrations", "columns": ["version", "checksum", "applied_at"], "indexes": [{"name": "PRIMARY", "columns": "version", "unique": 1}], "foreign_keys": []}
]';
SET @wisdom_versions = '[
  {
    "version": "001_learning_records.sql",
    "checksum": "4ce4e3d9091238723bcc8f0d1938247e99397ea6807eda64be21c3edff11aba6"
  },
  {
    "version": "002_account_rename.sql",
    "checksum": "a56e0712c4fdfe7d6e4aae5cd9a17d174056104cc3ed83d7a239957a77fd7321"
  },
  {
    "version": "003_teaching_relations.sql",
    "checksum": "4d7b1bb79769a5ce6701b1cda22306a30bda8b97d48ee88a82e00efe78e780d1"
  },
  {
    "version": "004_course_resources.sql",
    "checksum": "ee1e4911a8e4084512ad40386996a9366369b96699198eb3803c98315298e95f"
  },
  {
    "version": "005_account_access.sql",
    "checksum": "283739d568f5a77b4568cdcc8147974ce0a2befc5fec97b00e28aaf98f429f21"
  },
  {
    "version": "006_request_records.sql",
    "checksum": "83f0fabe24c26efae762c8d6cd958ec17773b833f94e1e1af27803f5cc81e042"
  }
]';

SELECT COUNT(*) INTO @wisdom_missing_columns
FROM JSON_TABLE(@wisdom_schema, '$[*]' COLUMNS (
    table_name VARCHAR(64) PATH '$.table',
    NESTED PATH '$.columns[*]' COLUMNS (column_name VARCHAR(64) PATH '$')
)) required_column
WHERE NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS c
    WHERE c.TABLE_SCHEMA=DATABASE() AND c.TABLE_NAME=required_column.table_name AND c.COLUMN_NAME=required_column.column_name);

SELECT COUNT(*) INTO @wisdom_missing_indexes
FROM JSON_TABLE(@wisdom_schema, '$[*]' COLUMNS (
    table_name VARCHAR(64) PATH '$.table',
    NESTED PATH '$.indexes[*]' COLUMNS (
        index_name VARCHAR(64) PATH '$.name', column_names VARCHAR(512) PATH '$.columns', is_unique INT PATH '$.unique'
    )
)) required_index
WHERE required_index.index_name IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM information_schema.STATISTICS s
    WHERE s.TABLE_SCHEMA=DATABASE() AND s.TABLE_NAME=required_index.table_name AND s.INDEX_NAME=required_index.index_name
    GROUP BY s.INDEX_NAME
    HAVING GROUP_CONCAT(s.COLUMN_NAME ORDER BY s.SEQ_IN_INDEX)=required_index.column_names
        AND MAX(s.NON_UNIQUE)=1-required_index.is_unique
);

SELECT COUNT(*) INTO @wisdom_missing_relations
FROM JSON_TABLE(@wisdom_schema, '$[*]' COLUMNS (
    table_name VARCHAR(64) PATH '$.table',
    NESTED PATH '$.foreign_keys[*]' COLUMNS (
        column_name VARCHAR(64) PATH '$.column', parent_table VARCHAR(64) PATH '$.parent',
        parent_column VARCHAR(64) PATH '$.parent_column', delete_rule VARCHAR(16) PATH '$.delete_rule',
        update_cascade INT PATH '$.update_cascade'
    )
)) required_fk
WHERE required_fk.column_name IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM information_schema.KEY_COLUMN_USAGE k
    JOIN information_schema.REFERENTIAL_CONSTRAINTS r
      ON r.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA AND r.TABLE_NAME=k.TABLE_NAME AND r.CONSTRAINT_NAME=k.CONSTRAINT_NAME
    WHERE k.CONSTRAINT_SCHEMA=DATABASE() AND k.TABLE_NAME=required_fk.table_name AND k.COLUMN_NAME=required_fk.column_name
      AND k.REFERENCED_TABLE_NAME=required_fk.parent_table AND k.REFERENCED_COLUMN_NAME=required_fk.parent_column
      AND r.DELETE_RULE=required_fk.delete_rule AND (required_fk.update_cascade=0 OR r.UPDATE_RULE='CASCADE')
);

SELECT COUNT(*) INTO @wisdom_migration_conflicts
FROM JSON_TABLE(@wisdom_versions, '$[*]' COLUMNS (version VARCHAR(128) PATH '$.version', checksum CHAR(64) PATH '$.checksum')) expected
JOIN schema_migrations existing ON existing.version=expected.version COLLATE utf8mb4_general_ci
WHERE BINARY existing.checksum<>BINARY expected.checksum;

SELECT COUNT(*) INTO @wisdom_pending_legacy
FROM user_wrongbook w JOIN users u ON BINARY u.username=BINARY w.user_id
WHERE NOT EXISTS (SELECT 1 FROM learning_wrongbook n WHERE n.legacy_id=w.id);

SET @wisdom_upgrade_ok = (@wisdom_missing_columns=0 AND @wisdom_missing_indexes=0
    AND @wisdom_missing_relations=0 AND @wisdom_migration_conflicts=0 AND @wisdom_pending_legacy=0);

INSERT INTO schema_migrations(version,checksum)
SELECT expected.version,expected.checksum
FROM JSON_TABLE(@wisdom_versions, '$[*]' COLUMNS (version VARCHAR(128) PATH '$.version', checksum CHAR(64) PATH '$.checksum')) expected
WHERE @wisdom_upgrade_ok AND NOT EXISTS (SELECT 1 FROM schema_migrations existing WHERE existing.version=expected.version COLLATE utf8mb4_general_ci);
COMMIT;

-- OK 且执行过程无报错才表示完成。非零缺项或校验和冲突需要核对，不要清空业务表重建。
SELECT IF(@wisdom_upgrade_ok, 'OK', 'NEEDS_ATTENTION') AS upgrade_status,
    DATABASE() AS current_database,
    (SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()) AS total_tables,
    @wisdom_missing_columns AS missing_columns,
    @wisdom_missing_indexes AS missing_indexes,
    @wisdom_missing_relations AS missing_relations,
    @wisdom_migration_conflicts AS migration_conflicts,
    (SELECT COUNT(*) FROM schema_migrations WHERE version COLLATE utf8mb4_general_ci IN (
        SELECT version COLLATE utf8mb4_general_ci FROM JSON_TABLE(@wisdom_versions, '$[*]' COLUMNS (version VARCHAR(128) PATH '$.version')) expected
    )) AS applied_migrations,
    @wisdom_pending_legacy AS pending_legacy_wrongbook,
    (SELECT COUNT(*) FROM user_wrongbook w WHERE NOT EXISTS (SELECT 1 FROM learning_wrongbook n WHERE n.legacy_id=w.id)) AS unmatched_legacy_wrongbook;
