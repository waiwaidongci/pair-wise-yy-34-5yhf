# 工伤事故调查与纠正措施

记录工伤经过、伤害、现场和证人，维护调查、纠正措施、验证与关闭流程。

## 模块结构

- `app.py`：参数解析、依赖组装和HTTP服务启动。
- `src/domain.py`：数据结构、错误、状态和基础校验。
- `src/rules.py`：状态机、角色矩阵、优先级、期限和关闭不变量。
- `src/repository.py`：SQLite建表、事务、版本控制和审计链。
- `src/service.py`：权限检查、用例编排、并发控制和审计。
- `src/http_api.py`：JSON路由和统一错误响应。
- `src/audit.py`：UTC时间和SHA-256审计事件。
- `static/index.html`：最小演示页。
- `tests/`：完整流程、规则和失败测试。

## 初始化与启动

```bash
python3 app.py --db ./data.db --port 8311
```

默认端口为`8311`，首次启动自动建库。使用`X-Actor`和`X-Role`请求头传递身份。

## 主要接口

- `GET /health`
- `GET /api/items`
- `POST /api/items`
- `GET /api/items/{id}`
- `POST /api/items/{id}/records`
- `POST /api/items/{id}/transition`，必须提交`expected_version`
- `GET /api/items/{id}/statements`
- `POST /api/items/{id}/statements`
- `POST /api/items/{id}/statements/{sid}/review`
- `GET /api/audit`

允许角色：reporter, investigator, safety_manager, viewer。严重度越高、伤害指数越大或未关闭措施越多，优先级越高；严重事故必须在4小时内启动调查。

## 现场陈述

- 调查员（investigator）按证人和观察位置分别登记原话：`POST /api/items/{id}/statements`，字段为`witness`、`position`、`content`。
- 同一证人同一观察位置重复提交时保留新版本（`version`递增、内容更新），该陈述已有的复核随之失效，回到待复核状态；每次提交的原话都写入审计链，可随时追溯。
- 安全员（safety_manager）逐条复核：`POST /api/items/{id}/statements/{sid}/review`，`verdict`取`consistent`（一致）、`conflict`（冲突）或`undetermined`（无法判断），必须填写`note`复核说明。
- 存在冲突或待复核（未判断）陈述时，事故不能从`corrective_action`进入`verification`，错误信息列出待复核人与冲突项。
- 事故详情与列表均返回`statement_summary`：`pending_review`（待复核人）与`conflicts`（冲突项）。

## 测试

```bash
python3 -m unittest discover -s tests -v
```
