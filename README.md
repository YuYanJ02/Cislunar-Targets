# 地月空间目标目录

一个可部署到 GitHub Pages 的静态目录页面。页面统一展示 Space-Track 与 Bill Gray 两个来源的目标登记信息、轨道根数、数据历元和源间差异。GitHub Actions 定时更新数据，浏览器端不保存或接触 Space-Track 凭据。

在线页面（部署后）：https://yuyanj02.github.io/Cislunar-Targets/

## 功能

- 按名称、NORAD、COSPAR 和别名检索
- 按数据来源、历元新鲜度和轨道类型筛选
- 查看半长轴、周期、偏心率、倾角、近远地点等轨道信息
- 同一目标存在两个来源时显示半长轴、周期和历元差异
- 导出当前筛选结果为 CSV 或 JSON
- GitHub Actions 定时刷新 Space-Track GP 和 Bill Gray TLE
- 按唯一历元追加保存 Space-Track 与 Bill Gray 历史根数，不覆盖旧记录
- 保留数据来源、抓取时间、源文件与提交版本

## 仓库结构

```text
.
├─ public/                       GitHub Pages 静态页面
│  ├─ index.html
│  ├─ assets/                    页面样式与交互
│  └─ data/catalog.json          统一后的当前目录
├─ data/registries/              可下载的 Excel 登记表与模板
├─ data/history/                 压缩的追加式轨道历史分片与索引
├─ docs/                         数据说明、维护方法与 API 指南
├─ scripts/                      导入、更新和校验脚本
└─ .github/workflows/            自动更新与 Pages 部署工作流
```

相关说明：

- [字段和统一规则](docs/data-dictionary.md)
- [更新、校验与部署流程](docs/maintenance.md)
- [数据符合性分析框架](docs/consistency-analysis.md)
- [数据来源、引用与许可边界](DATA_SOURCES.md)
- [项目引用元数据](CITATION.cff)
- [Space-Track API 操作指南](docs/guides/Space-Track_API数据检索与下载操作指南.docx)
- [登记表下载目录](data/registries/)

## 本地预览

```powershell
python -m http.server 4173 --directory public
```

打开 `http://localhost:4173/`。

## 第一次导入现有登记表

```powershell
python scripts/import_registry.py `
  --bill-gray-xlsx "../outputs/cislunar_target_registry/地月空间目标登记表_BillGray.xlsx" `
  --space-track-xlsx "../outputs/cislunar_target_registry/地月空间目标登记表_SpaceTrack.xlsx" `
  --output public/data/catalog.json
```

## 配置自动更新

1. 在 GitHub 新建仓库并推送本目录。
2. 在仓库 `Settings > Secrets and variables > Actions` 中增加：
   - `SPACETRACK_USERNAME`
   - `SPACETRACK_PASSWORD`
3. 在 `Settings > Pages` 中选择 `GitHub Actions` 作为部署来源。
4. 手动运行一次 `Update catalog and deploy Pages` 工作流。

工作流默认每天 02:15 UTC 运行。若未配置 Space-Track Secrets，任务仍会更新 Bill Gray 数据，但会保留现有 Space-Track 快照。

每次成功刷新后，脚本会按“来源 + 目标 + 轨道内容”生成 SHA-256 指纹，只把未出现过的历元追加到 `data/history/shards/`。首次运行还会读取目标对应的 Bill Gray 文件及其历史版本文件中的全部 TLE 对。历史分片使用 `JSONL.gz`，已生成的分片不再修改。

Secrets 只提供给 GitHub Actions 运行环境。不要把 Space-Track 用户名、密码、会话 Cookie 或 API 返回的认证信息写入源码、JSON、Excel 或工作流日志。

## 历史库查询与回溯

按 NORAD、来源和历元范围查询：

```powershell
python scripts/query_history.py `
  --history-root data/history `
  --norad 57754 `
  --source spacetrack `
  --start 2023-01-01 `
  --output aditya_l1_history.json
```

Space-Track 的 `GP` 只提供抓取时的最新根数。仓库从 2026-09 起按完整 UTC 自然月保存 `GP_HISTORY`：每月 1 日 03:35 UTC 自动归档上一个月，例如 2026-10 月归档 `2026-09-01` 至 `2026-09-30`，2026-11 月归档 `2026-10-01` 至 `2026-10-31`。`data/history/gp_history_months.json` 记录已完成月份，重复运行会直接跳过。

更早或指定目标的历史元素集可使用手动工作流 `Backfill Space-Track history` 分段回溯；同一 `GP_HISTORY` 时间区间不应重复下载。建议先按少量 NORAD 编号和月度时间区间试运行，成功归档后再处理下一批。

## 数据筛选口径

Space-Track 自动查询条件：

- `OBJECT_TYPE = PAYLOAD`
- `LAUNCH_DATE > 2000-12-31`
- `DECAY_DATE = null`
- `SEMIMAJOR_AXIS > 42164 km`

`DECAY_DATE = null` 只表示目录中没有再入日期，不能据此认定目标仍在正常运行。`SEMIMAJOR_AXIS > 42164 km` 是半长轴条件，也不表示目标任意时刻都位于 GEO 高度之外。

Bill Gray 更新器优先更新登记表中已有的源文件，并自动发现能够通过 NORAD 编号与当前 Space-Track 筛选结果匹配的新文件。Bill Gray 的 `H` 型扩展状态向量不是标准 TLE，页面会保存原始行和已有轨道摘要，但不会用普通 TLE 公式错误解析。

登记表中的 `mission_status=unknown` 必须保持为未知，除非存在独立、可追溯的任务状态来源。目录没有再入日期不能证明航天器仍在正常运行。

## 数据使用说明

Space-Track 官方允许转发基本 SSA 数据及基于这些数据的分析，但以适当注明来源为条件。本项目的自动更新当前使用 GP 类返回的 OMM/JSON 字段，查询口径与访问时间均在仓库和数据记录中保留。

Bill Gray 数据来自 [`Bill-Gray/tles`](https://github.com/Bill-Gray/tles)。截至 2026-10-13，该仓库根目录未声明适用于整库数据的许可证；本项目保留仓库、源文件和提交版本信息，但公开可访问不等于获得任意再许可权。

论文、报告或再发布数据时，请同时引用本项目与实际使用的原始来源。完整的推荐引用格式、查询 URL、可追溯字段及许可边界见 [DATA_SOURCES.md](DATA_SOURCES.md)；GitHub 的“Cite this repository”功能读取 [CITATION.cff](CITATION.cff)。

数据来源：

- https://www.space-track.org/
- https://www.space-track.org/documentation
- https://github.com/Bill-Gray/tles

## 范围与限制

- 页面展示的是轨道目录和研究用根数，不是实时测控系统。
- Space-Track GP/TLE/OMM 不应用于业务级碰撞预警。
- 两个来源相互接近只能说明源间一致，不能证明二者都接近真实轨道。
- 绝对精度评估需要精密星历、任务方轨道或独立测量作为外部参考。
- 地月空间高偏心率、L1/L2 和逃逸轨道可能使用非标准表示，不能一律按普通 SGP4 TLE 处理。

