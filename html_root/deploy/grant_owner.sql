-- 智算视界：仅为已存在的 rainbow_yu 账号启用主管理员权限。
-- 宝塔 phpMyAdmin：选中网站实际使用的数据库（wiscomper_com），执行本文件全文。
-- 这是数据库管理员执行的一次性授权，不放入通用安装脚本，不包含或修改密码。
SET NAMES utf8mb4;
START TRANSACTION;
SET @wisdom_owner_id = NULL;
SELECT id INTO @wisdom_owner_id
FROM users WHERE BINARY username = BINARY 'rainbow_yu' FOR UPDATE;

INSERT INTO account_access(user_id, role, disabled)
SELECT id, 'admin', 0 FROM users WHERE id = @wisdom_owner_id
ON DUPLICATE KEY UPDATE role = 'admin', disabled = 0;

INSERT INTO access_audit(actor_id, target_id, action, details)
SELECT user_id, user_id, 'provision_admin', JSON_OBJECT('source', 'baota_sql')
FROM account_access WHERE user_id = @wisdom_owner_id AND role = 'admin' AND disabled = 0;
COMMIT;

SELECT CASE
    WHEN @wisdom_owner_id IS NULL THEN 'ACCOUNT_NOT_FOUND'
    WHEN EXISTS(SELECT 1 FROM account_access WHERE user_id = @wisdom_owner_id AND role = 'admin' AND disabled = 0)
        THEN 'OWNER_ENABLED'
    ELSE 'NEEDS_ATTENTION'
END AS owner_status;

SELECT u.username, a.role, a.disabled
FROM users u JOIN account_access a ON a.user_id = u.id WHERE u.id = @wisdom_owner_id;
