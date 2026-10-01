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
2. 在「摊主」「挡柱」维护需求宽度与障碍位置；摊宽可在摊主页直接改。
3. 打开「柱间紧张度」查看**只读预估**：每个柱间空档的可落数 / 放不下数 / 放不下最宽摊宽。刷新此页不产生任何放置或运行。
4. 在紧张度表**恰好勾选一个柱间空档**后点「确认落库」：服务端按提交瞬间的摊主与挡柱重算并直接落库（无预占令牌）。未选中、多选、该空档放不下任何摊主都会被拦下且不增行。
5. 「分配带」只读展示已落库放置，并提供运行抽屉；「放不下」与主图、运行抽屉同源（`GET /api/allocate/state`），结论始终对齐。

### 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/allocate/tension` | 柱间紧张度表，纯只读，连刷不增行 |
| GET | `/api/allocate/state` | 主图/放不下/运行抽屉统一只读视图 |
| POST | `/api/allocate/confirm` | 体 `{segment_id, gap_indexes}`；`gap_indexes` 必须恰好 1 个，成功才写放置与运行 |
| PATCH | `/api/vendors/{id}` | 改 `stall_width_m`，下次确认跟新宽 |

## 开发与测试

```bash
docker compose exec api pytest -q
```
