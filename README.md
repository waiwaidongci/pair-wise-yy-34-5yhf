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
- `POST /api/items/{id}/statements`，按`witness_name`+`position`登记原话，重复提交升版本
- `POST /api/items/{id}/statements/{sid}/review`，提交`verdict`与`note`
- `GET /api/audit`

允许角色：reporter, investigator, safety_manager, viewer。严重度越高、伤害指数越大或未关闭措施越多，优先级越高；严重事故必须在4小时内启动调查。

## 现场陈述

- 调查员（investigator）按证人和观察位置分别登记原话；同一证人同一位置重复提交时保留新版本，旧版本及其复核随即失效。
- 安全员（safety_manager）逐条复核，结论为`consistent`（一致）、`conflicting`（冲突）或`undeterminable`（无法判断），并填写复核说明。
- 存在冲突、无法判断或未复核的陈述时，事故不能进入`verification`。
- 事故详情和列表中的`statement_summary`显示待复核人（`pending_witnesses`）与冲突项（`conflict_items`）。

## 测试

```bash
python3 -m unittest discover -s tests -v
```
