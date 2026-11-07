# 管理后台

## 功能介绍

只有管理员能看到。入口：「我的」页 → 管理 → 管理后台。分三个标签：

- **概览**：注册用户、7 天新注册、24 小时 / 7 天活跃；会员人数、7 天内到期、24 小时付款、30 天收入；待处理的意见反馈、内容报错、待审核单词、已停用账号；今天的复习次数和人数、AI 新生成条数、免费用户用掉的 AI 次数。点数字能跳到对应的列表。
- **用户**：按通德 ID、用户名、昵称、邮箱搜索（不分大小写），可以只看会员或已停用的账号，新注册的排在前面，一次显示 50 个。点一个用户进详情页，能看到基本信息、学习情况、付款记录和最近一天的免费次数用量，还能送会员、重置密码、停用 / 恢复账号。
- **内容**：反馈和报错、待审核单词、语法题库入口、邀请链接。这些以前在「我的」页，现在都挪到这里。

**停用账号**：被停用的人马上下线，不能再登录（密码对了也不行，提示“这个账号已被停用”），他的数据都还在，随时可以恢复。管理员自己不能被停用。

## 详细设计

- 后端 `admin.py`（Blueprint），所有接口都用 `auth.admin_required`：
  - `GET /api/admin/overview`：概览数字。`payments.month` 按币种列出最近 30 天的收入，`total` 以分为单位；“今天”的 AI 用量按管理员的本地日期算（`billing.today_key()`）。
  - `GET /api/admin/users?q=&filter=member|banned&offset=`：搜索，一页 50 个，多 `more / total`。每个用户带 `created_at / last_seen / banned / member_until / learned / me / admin`。原来在 `auth.py` 里的旧列表接口挪到这里，返回格式兼容。
  - `GET /api/admin/users/<id>`：详情，多 `member_last`（过期的会员也给）、`mastered`、`reviews_7d`、`last_review`、`added_words`、`lessons`、`feedback`、`payments`（最近 20 条）、`usage_day` 和 `usage`（最近一天的 `usage_daily`）。
  - `POST /api/admin/users/<id>/ban` `{banned, reason}`：停用 / 恢复。
- 停用：在 `user_settings` 里记 `banned`（值是原因），同时清掉登录令牌。`auth.check_login()` 每次请求都检查，被停用的会话直接清掉、返回 403；`auth.login_ok()` 先核对密码再检查停用，这样别人试不出哪个账号被停用了。
- 活跃：`auth.check_login()` 在 `user_settings` 里写 `last_seen`，同一个人最多每 10 分钟写一次（时间记在内存里，重启后会多写一次）。2026-11-08 才开始记。
- 注册时间：`users` 加了 `created_at` 列（迁移时自动加）。2026-11-08 之前注册的账号这一列是空的，页面上会写明“没有记录”。
- 送会员、重置密码、反馈、待审核、邀请码都还是原来的接口（`billing.py`、`auth.py`、`feedback.py`、`word_add.py`），只是页面挪了位置。
- 前端 `static/js/admin.js`，页面是 `#admin`（三个标签）和 `#auser`（用户详情），在 `core.js` 的 `PAGES` 里登记，入口由 `showAdminEntry()` 放到「我的」页。

## 变更记录

- 2026-11-08：第一版。加概览、用户搜索和详情、停用账号，注册时间和最近使用时间从这天开始记；「我的」页里的管理内容挪进后台。
