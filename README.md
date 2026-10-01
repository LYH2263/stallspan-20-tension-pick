# StallSpan 市集摊档开间

沿街段一维 First-Fit 开间分配，挡柱不可被摊位跨越，输出分配图与放不下清单。

技术栈：Python 3.12 / FastAPI / SQLAlchemy / PostgreSQL / Vue 3 / TypeScript / Vite

## 启动

```bash
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:4700 |
| API | http://localhost:9700 |
| API 文档 | http://localhost:9700/docs |
| Postgres | localhost:5448 |

健康检查：`GET http://localhost:9700/api/health`

## 使用说明

1. 在「集日」「街段」确认开市日与可用宽度。
2. 在「摊主」「挡柱」维护需求宽度与障碍位置。
3. 打开「柱间紧张度」查看每个柱间空档的**只读**预估：可落数、放不下数、放不下最宽摊宽。刷新任意次都不写库。
4. **恰好勾选一个柱间空档**，点「确认所选空档并落库」：系统按提交瞬间的摊主宽度与挡柱重算（不使用打开时的旧预估），单请求直接落库；零选、多选、空跑都会被拦下且不产生运行行。
5. 在「分配带」查看已落库主图、放不下名单与运行抽屉（三处同源 `/allocate/state`，结论一致）。

### 接口约定

| 方法 | 路径 | 写库 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/allocate/tension` | 否 | 柱间紧张度只读预估（可落数/放不下数/放不下最宽摊宽） |
| GET | `/api/allocate/state` | 否 | 主图、放不下、运行抽屉共用事实源 |
| POST | `/api/allocate/confirm` | 成功时 | 请求体 `{segment_id, span_keys}`；必须恰好一个空档键；空跑返回 409 且不建行 |

## 开发与测试

```bash
docker compose exec api pytest -q
```
