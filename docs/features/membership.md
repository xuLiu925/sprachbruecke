# 会员、免费次数和付款

## 功能介绍

- **免费版**：今日学习（背单词）、词库、查词、加词、语法基础不限次数；其他练习每天有次数：

  | 功能 | 免费版每天 |
  |---|---|
  | 冠词练习、听写 | 各 3 组 |
  | 句子练习 | 每种题型 2 组（填空、连词成句、中译德分开算） |
  | 定冠词、不定冠词 / kein / 物主冠词、动词现在时、完成时、动词搭配、复数、变格、变位 | 每种 2 组 |
  | 情景课 | 1 节新课（打开过的课以后随时能再看；自建的工作对话不算） |
  | 整句复习 | 1 轮 |

  用完了，页面会提示“今天的已经用完了”，可以直接去「我的」页开通会员。次数按手机或电脑的本地日期算，凌晨 4 点换日（和今日学习一样）。
- **会员**：所有练习不限次数。月卡 ¥18（30 天）、年卡 ¥128（365 天），一次性付款，**不会自动续费**；没到期再买，会接着往后加。管理员一直不限次数。
- **到期提醒**：会员还剩 3 天时，首页顶部出现提醒卡片（“去续费” / “知道了”，点“知道了”当天不再显示）；「我的」页还剩 7 天起显示倒数。到期后 7 天内，首页和「我的」页提示“会员已到期，现在是免费版”。绑定了邮箱的，还剩不到 3 天时收到一封提醒邮件，同一个到期时间只发一次，续费后下次快到期再发。
- **付款**：在「我的」页点“开通月卡 / 年卡” → 跳到 Stripe 的付款页（银行卡、支付宝、微信支付）→ 付完自动回到「我的」页，会员马上开通。
- **管理员**：成员列表里每个人后面有“会员”按钮，可以送几天会员，填 0 就是取消会员。

## 详细设计

### 涉及的文件

| 文件 | 内容 |
|---|---|
| `billing.py` | 免费次数 `LIMITS`、会员、Stripe 付款页、核对付款、webhook、管理员送会员 |
| `database.py` | `memberships`、`payments`、`usage_daily` 三张新表 |
| `lessons.py` | `/api/roleplay/due?count=1` 只返回数量（首页用，不算次数） |
| `static/js/core.js` | 每个请求带 `X-TZ`（时区）；收到 402 时弹出应用内的会员弹窗 `showPaywall()`（`index.html` 的 `#paysheet`：年卡 / 月卡直接去付款、明天再来、看看会员区别；关掉时在二级页面就退回上一页；AI 和会员功能的提示带 `stay`，关掉后留在原页）；付完款回来调 `checkPaid()` |
| `static/js/home.js` | 「我的」页会员卡片 `showMember()`、`checkPaid()`、管理员“会员”按钮 |
| `static/js/lessons.js` | 列表用 GET `/api/lessons`，打开课时才 GET `/api/lessons/<id>` 取课文 |

### 免费次数怎么算

- `billing.py` 用 `before_app_request` 统一检查：路径在 `LIMITS` 里、是 GET、用户不是会员也不是管理员，就先占一次（一条 SQL：没到上限才加 1，同时发几个请求也不会超），到上限返回 **402** `{error, paywall: true}`；接口最后没返回 200 就退回这一次（`after_app_request`），出错不扣次数。各练习模块的代码不用改。
- “今天”按用户记下的时区算（`user_settings` 的 `quota_tz`），时区变了（出国、夏令时）最多 24 小时改一次，免得来回改时区多拿次数。
- 按参数分开算的练习（句子练习的 `mode`），不带参数时按接口默认值（`cloze`）计数。
- 情景课新课先记一行再数今天开了几节，超了就删掉这行并返回 402。
- 一次请求 = 一组题。以后加新的练习接口，要在 `LIMITS` 里登记才会限次数。
- 情景课的课文在 `content/lessons.json`（不在 `static/`，不能直接下载）。课程列表 GET `/api/lessons` 只有标题、场景和词表；课文要 GET `/api/lessons/<id>`，和角色扮演接口 `/api/roleplay/lesson/<id>` 一样由 `LESSON_RE` 查次数。旧版前端用的 POST `/api/usage/lesson {id}` 还留着。每节课只在第一次打开那天记一行，`usage_daily` 里有这节课的记录就算“看过”。
- 日期：前端请求头 `X-TZ` = `getTimezoneOffset()`，用 `today.local_day()` 算本地日期。

### 付款流程

1. 前端 POST `/api/billing/checkout {plan: month|year}`，后端调 Stripe 建 Checkout 会话（人民币、一次性付款、`locale=zh`，不指定付款方式，Stripe 后台打开哪些就显示哪些），记进 `payments`（`status = open`），返回付款页网址。
2. 付完 Stripe 跳回 `/?paid=会话编号#me`，前端调 GET `/api/billing/confirm?session_id=`，后端向 Stripe 查这个会话。
3. Stripe 也会 POST `/api/stripe/webhook`（事件 `checkout.session.completed`、`checkout.session.async_payment_succeeded`），后端用 webhook 密钥核对签名（HMAC-SHA256，时间差不超过 5 分钟）。
4. 两条路都走 `grant()`：会话已付款、金额和币种和下单时一样，才把 `payments` 改成 `paid` 并加会员天数。改状态用 `UPDATE ... WHERE status != 'paid'`，同一笔只加一次。

没用 Stripe 的 Python 包，接口用标准库 `urllib` 调。

### 接口

| 方法 路径 | 说明 |
|---|---|
| GET `/api/billing` | `admin / until`（会员到期时间，不是会员为 null）`/ expired`（最近 7 天内到期的到期时间，否则 null）`/ enabled`（是否配置了收款）`/ plans / usage`（今天用了的功能） |
| POST `/api/billing/checkout` | `{plan}` → `{url}` 付款页 |
| GET `/api/billing/confirm?session_id=` | 只能核对自己的付款 → `{paid, until}` |
| POST `/api/stripe/webhook` | Stripe 调用，要签名 |
| GET `/api/lessons`、GET `/api/lessons/<id>` | 情景课列表（没有课文）；一节课的全文，没看过的新课超出返回 402 |
| POST `/api/usage/lesson` | `{id}` 旧版前端打开情景课前登记，超出返回 402 |
| POST `/api/admin/users/<id>/membership` | 管理员 `{days}`：加天数，0 = 取消 |

### 配置

服务器上的 `~/sprachbruecke/.stripe_config`（不进版本库，权限 600）：

```
{"secret_key": "sk_test_...", "webhook_secret": "whsec_..."}
```

也可以用环境变量 `STRIPE_SECRET_KEY`、`STRIPE_WEBHOOK_SECRET`。没配置时「我的」页显示“收款还没开通”，免费次数照样限制。Webhook 地址是固定网址 `/api/stripe/webhook`，在 Stripe 后台 Developers → Webhooks 里能看到。

### 从测试模式换成正式收款

1. Stripe 后台完成账户激活（身份、银行账户）。
2. 关掉测试模式，复制正式的 `sk_live_...`，在 Developers → Webhooks 建一个同样的 webhook（地址、两个事件），复制它的 `whsec_...`。
3. 把两个值写进服务器的 `.stripe_config`，重启服务。**正式密钥不要发给任何人。**

受限密钥（`rk_live_` 开头，选“完整访问权限（敏感操作除外）”）也能用，比完整私钥安全：泄露了也不能提现。

### 已知限制

- 课程列表里的词表（`glossary`）是公开给登录用户的，单词卡查词要用。
- AI 功能目前只有管理员能用，还没有开放给会员，也没有“每天 5 次”的限制。
- 不支持退款和自动续费；退款要在 Stripe 后台手动退，再用管理员“会员”按钮把天数减掉（填 0 取消后重新送）。
- 
## 变更记录

- 2026-11-03：新增。接口测试通过（假的 Stripe）；用测试密钥真实建过一次付款页（人民币 ¥18，显示银行卡、支付宝、微信支付、Link），webhook 已在 Stripe 建好。还没部署，页面没在浏览器里点过，也没真实走完一次付款。
- 2026-11-03：已部署，服务器上配置了测试密钥（`.stripe_config`）。用户在线上用测试卡走完一次付款，会员开通成功。
- 2026-11-03：堵住情景课绕过次数：课文从 `static/lessons.json` 挪到 `content/lessons.json`，改成走 `/api/lessons/<id>`，部署时删掉服务器上旧的静态文件。接口测试通过，还没部署，页面没点过。
- 2026-11-03：到期提醒。`/api/billing` 加 `expired`；首页提醒卡片和「我的」页倒数（`home.js` 的 `showMemberWarn()`、`MEMBER_SOON` / `MEMBER_WARN`）；提醒邮件 `member_mail.py`，由守护 `tools/watchdog.py` 每小时调一次，发过的记在 `user_settings` 的 `expiry_mail`，邮件日期按北京时间写。到期当天和到期后不发邮件。接口测试通过（假的发信）；本地浏览器看过首页卡片、去续费、知道了、「我的」页倒数。还没部署，没真的发出过到期邮件。
- 2026-11-04：换成正式收款：受限密钥 + 正式模式 webhook（tongde.pages.dev）。密钥用只读查询验证过；没有真实付款验证，等第一个用户付款时留意会员是否自动开通。
- 2026-11-04：免费次数用完的提示从浏览器自带的 `confirm()` 换成应用内底部弹窗：显示用完了哪个练习，年卡（标“约 ¥10.7 / 月，一次付清，不自动续费”）、月卡按钮直接建付款页，“明天再来”/ × / 点外面 / Esc 关掉后退回上一页，不留在没有题的空页面。本地浏览器按手机尺寸看过弹窗和“明天再来”；付款按钮没点（本地配置已是正式密钥）。同日已部署（`f4329aa`），没在真手机上看过。
- 2026-11-04：堵免费次数的三个小漏洞：同时发几个请求能超额（改成先占一次再退）、改时区能多拿一天（时区 24 小时只能改一次）、句子练习不带 `mode` 另算一份（按默认值 `cloze` 算）。接口测试通过，没部署。
