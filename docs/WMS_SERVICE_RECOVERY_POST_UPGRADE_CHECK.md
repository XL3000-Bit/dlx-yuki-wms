# WMS 服务恢复与升级后运行态检查

## 执行边界

- 执行日期：2026-09-02（America/Los_Angeles）
- 本次只恢复 WMS Python 后端与 Vite 前端，并执行只读运行态检查。
- 未修改 PDA、Settings 前端或 Java 后端代码。
- 未创建或重置用户、密码、令牌；未执行数据库写入测试。
- 数据库部署结论保持独立有效，不受本次运行态检查结果影响。

## 服务恢复

- 启动时间：2026-09-02 14:08:01 -07:00。
- 后端命令：`uvicorn app.main:app --host 0.0.0.0 --port 8000`。
- 后端实际监听进程：PID 13156，`0.0.0.0:8000`。
- 前端命令：`npm run dev -- --host 0.0.0.0`。
- 前端实际监听进程：PID 15428，`0.0.0.0:5173`。
- 日志目录：`C:\Users\XL\dlx-yuki-wms-runtime-logs\20260902_140801`。
- 后端日志确认 server process 启动、application startup complete、Uvicorn 开始监听，未见 traceback。
- 前端日志确认 Vite ready，未见 stderr 错误。

## HTTP 运行态检查

| 检查 | 结果 | 判定 |
| --- | --- | --- |
| 后端 `GET /health` | HTTP 200，`status=ok` | PASS |
| 前端 `GET /` | HTTP 200 | PASS |
| 前端代理 `GET /api/v1/company-profile`（无凭据） | HTTP 401 | PASS：代理及鉴权边界可达 |
| `POST /api/v1/auth/login`（明确不存在的探测账号） | HTTP 401，错误凭据 | PASS：登录路由可达；不等于有效登录通过 |
| Inbound 列表（无凭据） | HTTP 401 | 路由可达，认证后读取待验收 |
| Inventory 列表（无凭据） | HTTP 401 | 路由可达，认证后读取待验收 |
| FBA 列表（无凭据） | HTTP 401 | 路由可达，认证后读取待验收 |
| Outbound 列表（无凭据） | HTTP 401 | 路由可达，认证后读取待验收 |

## 当前状态

```text
DATABASE_SCHEMA_STATUS      = DEPLOYED_AND_CURRENT
APPLICATION_SERVICE_STATUS  = RUNNING
OPERATIONAL_AVAILABILITY    = PASS
WMS_POST_UPGRADE_RECOVERY   = COMPLETE
PDA_OPERATIONS_V1           = PARTIAL
PDA_DEVELOPMENT             = PAUSED
PDA_PRODUCTION_USE          = PROHIBITED
```

服务进程已恢复并保持运行。下述认证后只读验收已使用用户在本机手动建立的会话完成；PDA 模块继续暂停，不纳入本次恢复判定。

## AUTHENTICATED READ-ONLY ACCEPTANCE

### A-C. 会话、身份与权限范围

- 用户已在本机页面手动完成登录；验收仅使用该现有浏览器会话。
- 当前 URL 属于 `http://127.0.0.1:5173/`，页面处于 WMS 主界面而非登录页。
- 完整页面刷新后会话仍有效，`GET /api/v1/users/me` 返回 HTTP 200。
- 当前角色正常加载为 `ADMIN`；姓名、邮箱等身份字段已脱敏，不写入本报告。
- 五个受保护模块的只读访问均由当前权限正常放行，未出现意外 HTTP 403。
- 默认仓库字段和仓库选项正常加载，`GET /api/v1/master-data/warehouses` 返回 HTTP 200。数据库中的 `default_warehouse_id` 当前为合法未配置状态（NULL），并非加载失败。
- 未询问、读取、复制、显示或保存账号密码、Cookie、Access Token 或 Refresh Token；未从开发者工具提取认证秘密。

### D-I. Company Profile 与五项核心模块

所有动作仅为页面打开、刷新及页面自身发起的 GET。接口路径按当前项目实际路由记录，查询参数和业务标识已脱敏。

| 模块 | 方法与脱敏 URL | HTTP | 页面解析/数据状态 | 客户端页面检查耗时 | 前后端异常 |
| --- | --- | --- | --- | ---: | --- |
| Company Profile | `GET /api/v1/company-profile` | 200 | 唯一资料正常展示；`id=1`；未点击 Save | 1.94 s | 无业务异常 |
| Inbound | `GET /api/v1/inbound` | 200 | 分页首屏已有数据并正常渲染 | 1.94 s | 无业务异常 |
| Inventory | `GET /api/v1/inventory` | 200 | 分页首屏已有数据并正常渲染 | 1.94 s | 无业务异常 |
| FBA | `GET /api/v1/fba/workbench` | 200 | 分页首屏已有数据并正常渲染 | 1.93 s | 无业务异常 |
| Outbound | `GET /api/v1/outbounds/workbench` | 200 | 分页首屏已有数据并正常渲染；页面只读详情 GET 同为 200 | 1.93 s | 无业务异常 |

- 五项页面路由均正常打开，未回到登录页；没有 401、意外 403、HTTP 500、schema validation error 或 migration revision error。
- 上表耗时是浏览器端页面导航及基础渲染的观测值，并非服务端单接口 APM 耗时；本次未为测量耗时修改代码或增加埋点。
- Company Profile GET 前后数据库均只有一行：`id=1`、`singleton_key=1`；页面不存在重复公司资料。

### J-K. 前端控制台与后端日志

- 验收期间浏览器控制台未新增未处理异常。新增 7 条均为框架兼容/弃用警告：三次 `useForm` 连接提示、三次 Ant Design Card `bordered` 弃用提示、一次 Ant Design v5 与 React 19 兼容提示；不含业务数据或认证秘密，未影响本次页面解析。
- 后端访问日志确认上述认证后 GET 均为 HTTP 200。
- 后端日志未见 traceback、SQLAlchemy 错误、缺列错误或 migration revision 错误；字符串检索中的 3 个 `Exception` 命中均来自正常的 `/operational-exceptions` 路由名称，不是异常堆栈。
- 前端 stderr 无新增错误；后端 application startup complete 与前端 Vite ready 各出现一次，没有反复重启证据。

### L-N. 数据库只读复核与写入核验

- `alembic_version` 仍为唯一值 `20260902_0026`。
- Company Profile 仍为一行，`id=1`、`singleton_key=1`。
- Company Profile 的 CREATE/UPDATE 审计计数在 GET 前后均为 0，没有因只读访问增加。
- 38 张既有业务表的行数指纹在验收前后均为 `b84cfec99663c188514643087ec2145dd67b6ade667e742f328643a2692d3f04`，未发生意外行数变化。
- 本次验收没有执行 POST、PUT、PATCH、DELETE，没有点击写入或状态变更按钮，没有执行真实数据库写入测试。

### O-R. 最终运行状态、变更边界与剩余项

- `0.0.0.0:8000` 仍由 PID 13156 监听，`0.0.0.0:5173` 仍由 PID 15428 监听；两个原进程均保持运行且未改变启动方式。
- 最终 `GET /health` 返回 HTTP 200，`status=ok`。
- 未停止服务；FastAPI 与 Vite 进程没有异常退出或反复重启。
- 未修改代码、配置、数据库或冻结 migration；本文件是本次唯一追加的验收记录。
- 未运行指向真实数据库的 pytest，未执行 migration、stamp 或 downgrade。
- 未修改 PDA、Settings 前端或 Java；未 stage、commit 或 push。
- 恢复判定无剩余阻塞项。上述 7 条前端框架警告属于非阻塞技术债，不影响本次认证后只读验收结论。

```text
AUTHENTICATED_SESSION_READY = YES
AUTHENTICATED_SESSION_ACCESS = PASS
AUTH_SESSION_EXPIRED         = NO
DATABASE_SCHEMA_STATUS       = DEPLOYED_AND_CURRENT
REAL_DB_CURRENT              = 20260902_0026
APPLICATION_SERVICE_STATUS   = RUNNING
HEALTH_CHECK                 = PASS
UNAUTHENTICATED_GUARDS       = PASS
AUTHENTICATED_READ_ONLY      = PASS
BUSINESS_WRITE_DURING_CHECK  = NONE
OPERATIONAL_AVAILABILITY     = PASS
WMS_POST_UPGRADE_RECOVERY    = COMPLETE
PDA_DEVELOPMENT              = PAUSED
PDA_PRODUCTION_USE           = PROHIBITED
```
