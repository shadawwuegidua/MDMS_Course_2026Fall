# 第一阶段 API 说明

程序使用 Flask 提供网页和接口。网页地址返回 HTML；`/api/` 地址返回 JSON。标识 `id` 是 MongoDB ObjectId 的 24 位十六进制字符串。

## 登录与请求约定

注册、登录使用网页表单，成功后服务器设置签名会话 Cookie。后续请求由浏览器自动携带 Cookie。`GET /api/session` 返回当前账号和 `csrf_token`；修改数据的请求须将这个令牌放入 `X-CSRF-Token` 请求头，普通表单则使用隐藏的 `csrf_token` 字段。

JSON 请求设置 `Content-Type: application/json`。除 `/health`、首页及账号入口外，问卷业务需登录；匿名填写也需登录。

常用错误：400 为输入或令牌错误，401 为未登录，404 为不存在或不属于当前用户的管理资源，409 为状态冲突、截止、关闭或禁止重复，503 为数据库暂时不可用。错误 JSON 的 `error` 给出原因；答案错误还可包含 `question_id`。

## 账号与网页

| 方法 | 地址 | 输入及结果 |
|---|---|---|
| GET / POST | `/register` | 表单 `username,password,csrf_token`；用户名 3—40 字符，密码 6—128 字符；成功 302 并自动登录。 |
| GET / POST | `/login` | 同上；登录成功 302；账号或密码不正确为 400。可用 `next` 返回原填写页，仅允许站内路径。 |
| POST | `/logout` | 表单令牌；退出后 302。 |
| GET | `/api/session` | `{user: null或{id,username}, csrf_token}`。 |
| GET | `/dashboard` | 当前用户自己的问卷列表。 |
| GET | `/surveys/new` | 新建问卷页面。 |
| GET | `/surveys/<id>/edit` | 所有者的草稿编辑页。 |
| GET | `/survey/<id>` | 已发布且未截止的填写页。 |
| GET | `/survey/<id>/thanks` | 当前用户提交成功后的页面。 |
| GET | `/surveys/<id>/statistics` | 所有者的统计页，可带 `question_id`。 |
| GET | `/health` | 数据库连接正常时 `{status:"ok",database:"connected"}`。 |

## 问卷接口

| 方法 | 地址 | 输入或返回 |
|---|---|---|
| GET | `/api/surveys` | 所有者自己的 `{surveys:[问卷对象]}`。 |
| POST | `/api/surveys` | 完整问卷定义，创建草稿；201 返回 `{id,redirect}`。 |
| GET | `/api/surveys/<id>` | 仅所有者，返回问卷对象本身。 |
| PUT | `/api/surveys/<id>` | 仅草稿可更新完整定义；200 返回 `{id,message}`。 |
| POST | `/api/surveys/<id>/publish` | 无业务参数，可传 `{}`；至少一题、截止时间未到；返回 `{id,fill_url}`。若另一个标签页修改了检查过的题目或截止时间，返回 409，避免错误发布。 |
| POST | `/api/surveys/<id>/close` | 无业务参数；关闭后保留答卷和统计。 |
| PATCH | `/api/surveys/<id>/deadline` | `{deadline:"带时区的ISO时间"}` 或 `{deadline:null}`；已关闭时不能修改。 |
| GET | `/api/public/surveys/<id>` | 登录者读取可填写的问卷定义，不含创建者账号或任何答卷。 |

创建、更新所需定义：`title,description,is_anonymous,allow_multiple,deadline,questions`。布尔字段必须为 JSON `true/false`；不设截止时间用 `null`。问卷定义的完整例子见 `samples/demo_survey.json`，题目字段见 `数据库设计.md`。

返回问卷对象包含 `id,title,description,status,is_anonymous,allow_multiple,deadline,questions,created_at,updated_at`。日期返回 ISO 字符串，数据库保存 UTC 日期。

## 填写与统计接口

| 方法 | 地址 | 输入或返回 |
|---|---|---|
| POST | `/api/surveys/<id>/check-answer` | `{question_id,value}`；校验当前一题并返回 `{answer,next_id}`；下一题为空时 `next_id:null`。只检查，不保存答卷。 |
| POST | `/api/surveys/<id>/responses` | `{answers:{题目标识:答案}}`；服务器重新计算路径、校验并保存；201 返回 `{id,redirect}`。 |
| GET | `/api/surveys/<id>/statistics` | 仅所有者；返回 `total_responses,questions,responses`。 |
| GET | `/api/surveys/<id>/statistics?question_id=q_age` | 只返回所选题目的统计和答案字段，总答卷数仍是整个问卷的答卷数。 |

答案格式例子：

```json
{"answers":{"q_path":"no","q_age":"16","q_feedback":null}}
```

选择题使用选项标识，多选使用标识数组，文本使用字符串，数字可传数值或数值字符串。上例保存时年龄规范化为整数 16，并跳过水果及成年建议题；选填留空保存 `null`，不在路径上的答案丢弃。不能混入其他问卷的题目标识。

每题统计包含 `id,title,type,answered,options,values,average`。选择题 `options` 为 `{id,text,count}` 列表；填空的 `values` 为有效内容；数字 `average` 为平均值，无有效数字时为 `null`。答卷明细 `responses` 包含答卷标识、提交时间、显示身份和答案。匿名时身份固定为“匿名”，不输出内部填写者 ID。
