-- 智算视界 · 单文件安装与升级 · MySQL 8.0+
-- 宝塔：先备份当前库，在 phpMyAdmin 左侧选中 wiscomper_com，再点 SQL，粘贴本文件全部内容执行。
-- 使用当前选中的数据库，不创建数据库、不切换库名，不需要 CREATE DATABASE 权限。
-- 支持新库与原网站 18 表版本，补齐至 25 表，保留账户、算式、课包和旧错题。
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

-- 7. 应用升级记录（保留已有记录，由应用按校验和确认迁移）
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
COMMIT;

-- phpMyAdmin 最后显示当前库、已建表数量和保留待处理的旧错题数量。
SELECT DATABASE() AS current_database,
    (SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()) AS total_tables,
    (SELECT COUNT(*) FROM user_wrongbook w WHERE NOT EXISTS (SELECT 1 FROM learning_wrongbook n WHERE n.legacy_id=w.id)) AS unmatched_legacy_wrongbook;
