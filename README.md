# 基于 MongoDB 的问卷系统

仓库：[MDMS_Course_2026Fall](https://github.com/shadawwuegidua/MDMS_Course_2026Fall)

课程项目第一阶段，已实现注册登录、问卷创建与发布、三类题型（填空分文本和数字）、可配置跳转、答案校验、答卷保存和统计。界面使用普通 HTML、CSS 和 JavaScript，后端为 Flask，业务数据全部存储在 MongoDB。

## 文档入口

| 文档 | 可编辑版本 | PDF 版本 |
|---|---|---|
| 项目完成报告 | [Markdown](docs/项目完成报告.md) | [课程提交 PDF](docs/pdf/2026_ECNU_PJ1_1_庄子由.pdf) |
| 数据库设计与查看命令 | [Markdown](docs/数据库设计.md) | [PDF](docs/pdf/数据库设计.pdf) |
| API 说明 | [Markdown](docs/API说明.md) | [PDF](docs/pdf/API说明.pdf) |
| 测试报告 | [Markdown](docs/测试报告.md) | [PDF](docs/pdf/测试报告.pdf) |
| 技术讲解与检查指南 | [Markdown](docs/技术讲解与检查指南.md) | [PDF](docs/pdf/技术讲解与检查指南.pdf) |
| AI 使用日志 | [Markdown](docs/AI使用日志.md) | [PDF](docs/pdf/AI使用日志.pdf) |

第一次了解项目，可先看技术讲解与检查指南，按照“网页操作 → 后端逻辑 → MongoDB 数据”的顺序检查。课程要求的项目完成报告单独位于 `docs/pdf/`，其最前面提供仓库链接。

## 主要功能

- 注册、登录，用户只能管理自己的问卷和统计。
- 创建草稿，添加与排序题目，配置选项、校验和跳转规则。
- 发布分享链接，设置截止时间或关闭问卷。
- 支持匿名显示、重复填写设置、逐题作答和最终提交。
- 查看整份问卷或某道题的选项计数、填写内容及数字平均值。

数据库分为 `users`、`surveys`、`responses` 三个集合。题目、选项与规则嵌入问卷，每份答卷独立保存。结构图、字段和索引详见数据库设计。

## 环境与安装

本次实际运行环境为 Python 3.12.7、MongoDB Community Server 8.3.11，依赖版本已锁定。需要先安装 Python 与 MongoDB，并将 `mongod` 加入 PATH。

在本文件所在目录打开 PowerShell，首次运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

本机已创建 `.venv` 并安装依赖后，不需要重复安装。无需激活虚拟环境，直接使用其中的 Python 即可。

## 启动

第一个终端启动 MongoDB：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_mongo.ps1
```

`mongod` 需可在 PATH 中找到。数据库仅监听 `127.0.0.1:27017`，数据保存在本项目的 `work/mongodb/data`，日志保存在 `work/mongodb/mongod.log`。如果已有 MongoDB 在该端口运行，直接使用现有实例，不要再运行此脚本；本项目只使用 `.env` 中指定的数据库。

第二个终端启动网页程序：

```powershell
.\.venv\Scripts\python.exe app.py
```

打开 <http://127.0.0.1:5000/>，注册账号后创建问卷。<http://127.0.0.1:5000/health> 返回数据库连接状态。两个终端分别按 Ctrl+C 停止服务。

基本使用：创建问卷 → 添加题目与规则 → 保存草稿 → 发布 → 复制链接 → 填写者登录作答 → 创建者查看统计。发布后题目和重复填写设置固定，仍可调整截止时间或关闭问卷。

## 演示与测试

MongoDB 运行后，可在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe scripts\seed_demo.py
```

创建本地演示账号 `demo_owner`（问卷创建者）和 `demo_user`（填写者），共同演示密码为 `Demo12345!`。这是专门提供的本地演示口令。脚本生成一份五题问卷和两份有效答卷，重复运行不覆盖或重复添加。新的提交会改变演示统计，请先按检查指南核对初始数据。

运行全部自动化测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

共 49 项：23 项纯逻辑测试、26 项真实 MongoDB 集成测试。MongoDB 需运行，网页服务不必运行。集成测试生成随机独立数据库，结束后只清理该测试数据库，不使用正常的 `survey_stage1`。测试结果与原始输出见 `docs/测试报告.md`、`docs/测试原始输出.txt`。

## 配置

`.env` 可以设置 `MONGO_URI`、`MONGO_DB`、`SECRET_KEY`、`PORT`；不创建 `.env` 时也可使用默认本地配置。

默认数据库为 `survey_stage1`。首次启动自动创建三个集合、基础字段校验和索引，重复启动不会清空数据。修改 `schema.json` 不会自动改写已有集合的校验规则；如后续确需调整，会单独处理并记录。

`SECRET_KEY` 留空时每次启动随机生成；需要重启后保留登录状态时，在自己的 `.env` 中设置固定随机值。`.env`、虚拟环境和数据库原始文件不放入提交包。

## 项目文件

- `app.py`：页面、账号、权限和 HTTP API；调用业务逻辑与数据库。
- `logic.py`：题目配置校验、答案校验、跳转与统计。
- `db.py`：数据库连接、集合初始化、索引。
- `schema.json`：MongoDB 实际使用的集合校验规则。
- `templates/`、`static/`：网页模板、样式及编辑/填写交互。
- `scripts/start_mongo.ps1`：本地 MongoDB 启动脚本。
- `scripts/seed_demo.py`、`samples/`：可复现的本地演示数据。
- `tests/`：纯逻辑与真实数据库集成测试。
- `docs/`：项目报告、数据库/API 说明、测试、AI 日志、检查指南。

## 提交范围

提交包包含源码、依赖与配置示例、演示脚本及全部正式文档；不包含 `.venv`、`.env`、`work`、数据库原始目录、缓存、Word 临时锁文件及题目说明原件。解压后按本说明安装和运行即可。

本项目按第一阶段初始需求实现。题库、题目共享、版本历史和跨问卷统计留待第二阶段；未开展公网部署或大规模压力测试。

## 技术参考

- [Flask 安装与虚拟环境](https://flask.palletsprojects.com/en/stable/installation/)
- [PyMongo 连接 MongoDB](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/connect/mongoclient/)
- [MongoDB JSON Schema 校验](https://www.mongodb.com/docs/manual/core/schema-validation/specify-json-schema/)
- [MongoDB 部分索引](https://www.mongodb.com/docs/manual/core/index-partial/)
