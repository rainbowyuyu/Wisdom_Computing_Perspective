# 旧账户与邮箱兼容

新工作台可直接使用旧站 MySQL 的 `users` 和 `account_access`。旧用户 ID、用户名、邮箱和 bcrypt 密码哈希保留，不复制明文密码，也不把数据库用户表替换成 GitHub 用户表。GitHub 与邮箱账号分别按稳定身份识别；同名或同邮箱不会自动合并。

## 字段与数据来源

| 旧表 | 实际字段与用途 |
|---|---|
| `users` | `id` 整数主键；`username` VARCHAR(255) 唯一；`hashed_password` VARCHAR(255)；`email` VARCHAR(254)、ASCII 唯一；`email_verified`；`email_verified_at`；`created_at` |
| `account_access` | `user_id` 对应 users.id；`role` 仅 member/vip/admin；`disabled`；`daily_limit` 可空；`updated_at` |
| `account_email_codes` | 账户/邮箱/用途绑定的验证码摘要、到期、消耗时间、失败次数；`requester_ip_hash` 是 CHAR(64) |
| `account_email_limits` | 持久化限流桶、窗口开始时间和使用量 |

`users` 没有 role/status 列。缺少 `account_access` 记录时为 member；停用用户拒绝登录及后续访问。用户名、GitHub 昵称或邮箱都不产生权限。`daily_limit=0` 表示该账户没有个人调用额度，NULL 交由新工作台的站点默认额度策略处理；VIP/admin 可免个人额度限制，但仍记录调用并受站点总预算限制。旧站的历史计量表不改写成新场景模型调用数。

密码沿用 bcrypt `$2a$`/`$2b$` 等库支持的格式，不在登录时批量重新哈希。新设密码至少6字符且 UTF-8 不超过72字节；新用户名1–64字符，旧用户名登录允许到255字符。邮箱做小写与 IDNA 域名规范化。

## 配置与部署

`LEGACY_ACCOUNT_BACKEND=mysql` 显式选择旧库；`LEGACY_MYSQL_HOST/PORT/USER/PASSWORD/DATABASE` 对应旧 `MYSQL_HOST/PORT/USER/PASSWORD/DB`。数据库连接不可用、字段缺失或身份查询失败时返回服务错误，不退回 SQLite 创建同名账号。MySQL 连接不自动建表、修改结构或执行旧迁移。

`LEGACY_ACCOUNT_BACKEND=sqlite` 使用 Store 数据文件同目录的 `legacy-accounts.sqlite3`，建立兼容的 users/access/email 字段。它适用于独立本地部署和隔离测试，里面没有预设账户或管理员。测试必须显式选 SQLite 并使用临时 Store，不能让真实旧库承受测试写入。

[`database/legacy-accounts-bootstrap.sql`](../database/legacy-accounts-bootstrap.sql) 是供新 MySQL 数据库审阅的基线，不由程序执行。现有旧库应先核对字段与索引；早于邮箱迁移的数据库，需要运营者备份后审阅原站007/008邮箱迁移。不要运行 DROP、覆盖导入或重建 users。连接账户仅需账户/验证码表的必要读写及资料表的只读权限，不需要 DDL 权限。

SMTP 继续使用 `SMTP_HOST/PORT/USERNAME/PASSWORD/FROM/FROM_NAME/USE_TLS`。465使用隐式TLS，其余端口先 STARTTLS；不允许禁用 TLS。设置了用户名却缺少密码会标为未配置。`EMAIL_CODE_SECRET` 至少32字符，服务端存放；共享旧验证码表时使用原密钥以保持摘要兼容。所有这些配置只在服务端，`.env` 已列入忽略文件。`email_status()` 只判断配置完整性，不进行网络检查，不能表示发信已验证成功。

部署前应在目标环境执行只读数据库预检，确认账户、角色与邮箱表的字段和权限兼容。保留原私有配置，不把数据库凭据或用户统计写入公开报告。预检步骤见[部署包说明](../deploy/DEPLOY-PACKAGE.md)。

## 邮箱证明与会话

验证码为6位随机数字，10分钟有效，摘要为 HMAC-SHA256，绑定 email/purpose/user_id。新验证码使同用途、同账户的旧码失效。验证码校验和注册/绑定邮箱/改密码在同一数据库事务完成；错误尝试次数独立提交，5次后不能再使用。限流含60秒邮箱冷却、每日邮箱10次、来源30次及全站500次。密码登录另有15分钟标识符12次、来源60次限制。

注册、重设的对外发码消息保持一致，不透露邮箱是否存在；不存在邮箱不发邮件，投递失败会消耗本次证明。已登录邮箱验证遇到发送失败可显示错误。SMTP模板从旧站改编，保留HTML邮件和纯文本备选，不调用旧站模块，不强制链接旧域名。自动化用例使用模拟投递，真实发信需在运营环境单独验证。

`Store.login_legacy` 将匿名工作区事务归入对应账户并轮换会话/CSRF。外部身份键使用 `legacy:<数据源namespace>:<users.id>`，与 GitHub 数字ID隔离；既有 accounts 表的 github_id 列作为兼容唯一外部键使用。namespace 绑定 MySQL 主机/端口/库名或本地文件位置；改变来源不会把另一个库的同数字ID当作原账户。

每次请求重新读取可信角色和停用状态。每个会话在登录时独立保存 `credential_version`（bcrypt哈希的SHA256指纹），不跟随共享用户资料更新，公有响应不包含该字段。旧站改密后，旧设备请求失效，新密码登录的新设备仍保持有效。没有可信指纹的历史邮箱会话要求重新登录。新站重设接口同时撤销该身份的新站浏览器与内部渲染会话；旧站自己的会话存储不由新程序控制。

## 旧学习资料

`LegacyAccounts.import_library(user_id, owner)` 必须先验证该工作区 owner 确实映射到该旧 user_id。再从可信ID查到用户名，并用参数查询读取其 `formulas`、`example_video_notes`、`learning_wrongbook` 以及尚未被新错题表代表的 `user_wrongbook`。

符合新结构的公式、笔记和错题复制为新工作区记录；稳定源ID映射使重复登录或重试不会重复添加，也不覆盖用户后来在新工作台的修改。旧视频ID与时间点以纯文字保留，不伪装为新项目播放链接。旧复习计数不变成新站的实际复习成绩。原表不删除、不归档、不回写。

读取与新空间容量有上限；超长内容、未知格式或容量不足时返回 warning，原内容仍在旧库。一次最多读取200条公式、300条视频笔记和各300条新/旧错题，再按新空间容量写入。旧视频媒体、评论弹幕、脚本、课程附件及完整复习历史不在此自动迁入范围；这不是整库克隆或双向同步。

## 集成接口与验证

`LegacyAccounts(get_settings, get_store, sender=None)` 提供 `authenticate(identifier,password,requester_ip='')`、`get_user(id)`、`email_status()`、`send_code(email,purpose,requester_ip='',user_id=None)`、`register(username,password,email,code)`、`verify(user_id,email,code)`、`reset(email,code,new_password)`、`import_library(user_id,owner)`。账户结果为可信profile；错误统一 `AccountError(message,status,code)`，不携带驱动原始错误或凭据。路由层继续负责来源/CSRF检查、操作序列、会话轮换及公有字段筛选。

`tests/test_legacy_accounts.py` 使用临时SQLite、随机测试密钥及mock邮件，覆盖旧bcrypt、实时角色与停用、验证码用途/账户/到期/尝试次数、并发单次消费、重设与会话撤销、身份来源隔离、MySQL失败不降级、资料只读去重、SMTP TLS/模板和不限个人额度时的真实计量。真实SMTP投递和外部GitHub授权仍需运营环境另行验证。
