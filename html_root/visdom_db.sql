-- 智算视界完整数据库结构 · MySQL 8.0+
-- 单文件初始化入口：创建数据库及全部 25 张表、主键、外键、唯一约束与索引。
-- 无需 SOURCE 其他 SQL，也无需先启动 Python 服务或执行迁移文件。
-- 按外键依赖顺序创建，可重复导入，不包含用户数据，不清空现有表。
-- CREATE TABLE IF NOT EXISTS 不改变已存在表的结构；旧库升级仍使用迁移工具。
-- 新安装（任意终端）：mysql -u USER -p --default-character-set=utf8mb4 --execute="source visdom_db.sql"
-- 也可在 MySQL 客户端执行：SOURCE D:/项目目录/html_root/visdom_db.sql
-- 更换数据库名称时，同时修改下方 CREATE DATABASE 与 USE。
-- 现有数据库升级：python scripts/migrate_database.py --apply
CREATE DATABASE IF NOT EXISTS visdom_db CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE visdom_db;
SET NAMES utf8mb4;
SET time_zone = '+00:00';

-- 1. 账户与偏好
-- users
CREATE TABLE IF NOT EXISTS `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(255) NOT NULL,
  `hashed_password` varchar(255) NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- user_settings
CREATE TABLE IF NOT EXISTS `user_settings` (
  `user_id` varchar(64) NOT NULL,
  `settings_json` text,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- user_profiles
CREATE TABLE IF NOT EXISTS `user_profiles` (
  `user_id` varchar(255) NOT NULL,
  `avatar_url` varchar(512) DEFAULT NULL,
  `nickname` varchar(128) DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`),
  CONSTRAINT `fk_user_profiles_username` FOREIGN KEY (`user_id`) REFERENCES `users` (`username`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 2. 算式、完整题解、脚本、智能体模板与成就
-- formulas
CREATE TABLE IF NOT EXISTS `formulas` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` varchar(255) NOT NULL,
  `latex` text NOT NULL,
  `note` varchar(255) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_formulas_owner_created` (`user_id`,`created_at`,`id`),
  CONSTRAINT `fk_formulas_username` FOREIGN KEY (`user_id`) REFERENCES `users` (`username`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- animation_scripts
CREATE TABLE IF NOT EXISTS `animation_scripts` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` varchar(255) NOT NULL,
  `note` varchar(255) DEFAULT '',
  `code` mediumtext NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_scripts_owner_created` (`user_id`,`created_at`,`id`),
  CONSTRAINT `fk_animation_scripts_username` FOREIGN KEY (`user_id`) REFERENCES `users` (`username`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- agent_templates
CREATE TABLE IF NOT EXISTS `agent_templates` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` varchar(255) NOT NULL,
  `name` varchar(256) NOT NULL DEFAULT '未命名',
  `prompt` text NOT NULL,
  `steps_json` mediumtext,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_templates_owner_created` (`user_id`,`created_at`,`id`),
  CONSTRAINT `fk_agent_templates_username` FOREIGN KEY (`user_id`) REFERENCES `users` (`username`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 3. 课包、教案与课堂视频
-- course_packs
CREATE TABLE IF NOT EXISTS `course_packs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` varchar(64) NOT NULL,
  `name` varchar(128) NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_packs_owner_created` (`user_id`,`created_at`,`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- course_pack_documents
CREATE TABLE IF NOT EXISTS `course_pack_documents` (
  `pack_id` int NOT NULL,
  `description` text NOT NULL,
  `lesson_json` longtext NOT NULL,
  `revision` int NOT NULL DEFAULT '1',
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`pack_id`),
  CONSTRAINT `fk_pack_document` FOREIGN KEY (`pack_id`) REFERENCES `course_packs` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- course_pack_videos
CREATE TABLE IF NOT EXISTS `course_pack_videos` (
  `pack_id` int NOT NULL,
  `video_id` varchar(128) NOT NULL,
  `sort_order` int DEFAULT '0',
  PRIMARY KEY (`pack_id`,`video_id`),
  KEY `ix_pack_order` (`pack_id`,`sort_order`),
  CONSTRAINT `fk_pack_video` FOREIGN KEY (`pack_id`) REFERENCES `course_packs` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 4. 视频互动、观看进度、收藏与笔记
-- example_video_likes
CREATE TABLE IF NOT EXISTS `example_video_likes` (
  `video_id` varchar(128) NOT NULL,
  `user_id` varchar(64) NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`video_id`,`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- example_video_comments
CREATE TABLE IF NOT EXISTS `example_video_comments` (
  `id` int NOT NULL AUTO_INCREMENT,
  `video_id` varchar(128) NOT NULL,
  `user_id` varchar(64) NOT NULL,
  `content` text NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_comments_video_created` (`video_id`,`created_at`,`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- example_play_history
CREATE TABLE IF NOT EXISTS `example_play_history` (
  `user_id` varchar(64) NOT NULL,
  `video_id` varchar(128) NOT NULL,
  `progress` double NOT NULL DEFAULT '0',
  `last_active` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`,`video_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- user_favorites
CREATE TABLE IF NOT EXISTS `user_favorites` (
  `user_id` varchar(64) NOT NULL,
  `video_id` varchar(128) NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`,`video_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- watch_later
CREATE TABLE IF NOT EXISTS `watch_later` (
  `user_id` varchar(64) NOT NULL,
  `video_id` varchar(128) NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`,`video_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- learning_wrongbook_tags
CREATE TABLE IF NOT EXISTS `learning_wrongbook_tags` (
  `entry_id` bigint unsigned NOT NULL,
  `tag` varchar(64) NOT NULL,
  PRIMARY KEY (`entry_id`,`tag`),
  KEY `ix_wrongbook_tag` (`tag`,`entry_id`),
  CONSTRAINT `fk_wrongbook_tag_entry` FOREIGN KEY (`entry_id`) REFERENCES `learning_wrongbook` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 7. 应用升级记录（保持为空，由迁移程序按实际执行情况登记）
-- schema_migrations
CREATE TABLE IF NOT EXISTS `schema_migrations` (
  `version` varchar(128) NOT NULL,
  `checksum` char(64) NOT NULL,
  `applied_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
