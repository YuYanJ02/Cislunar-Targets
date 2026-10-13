# 更新、校验与部署流程

## 自动流程

GitHub Actions 工作流位于 `.github/workflows/update-catalog.yml`，默认每天 02:15 UTC 运行：

1. 检出本仓库。
2. 安装 Python 依赖。
3. 浅克隆 `Bill-Gray/tles`。
4. 使用 GitHub Secrets 登录 Space-Track。
5. 查询满足当前筛选口径的 GP 数据。
6. 更新已有 Bill Gray 文件，并发现能够按 NORAD 匹配的新候选。
7. 将未出现过的当前历元和 Bill Gray 历史 TLE 追加到压缩历史分片。
8. 校验统一目录、历史分片哈希和去重索引。
9. 仅在数据发生变化时提交 `public/data/catalog.json` 与 `data/history/`。
10. 将 `public/` 部署到 GitHub Pages。

数据更新提交不会再次触发同一工作流，避免自动提交形成循环。

## 必需配置

在仓库 `Settings > Secrets and variables > Actions` 中配置：

- `SPACETRACK_USERNAME`
- `SPACETRACK_PASSWORD`

在 `Settings > Pages` 中选择 `GitHub Actions` 作为来源。

## 手动更新

安装依赖：

```bash
python -m pip install -r requirements.txt
```

导入 Excel 登记表：

```bash
python scripts/import_registry.py \
  --bill-gray-xlsx data/registries/地月空间目标登记表_BillGray.xlsx \
  --space-track-xlsx data/registries/地月空间目标登记表_SpaceTrack.xlsx \
  --output public/data/catalog.json
```

更新在线数据：

```bash
git clone --depth 1 https://github.com/Bill-Gray/tles.git .cache/bill-gray-tles
python scripts/update_catalog.py \
  --catalog public/data/catalog.json \
  --bill-gray-dir .cache/bill-gray-tles \
  --output public/data/catalog.json

python scripts/archive_history.py \
  --catalog public/data/catalog.json \
  --bill-gray-dir .cache/bill-gray-tles \
  --history-root data/history
```

校验：

```bash
python scripts/validate_catalog.py public/data/catalog.json
python scripts/validate_history.py data/history --recent 5
node --check public/assets/app.js
```

历史查询示例：

```bash
python scripts/query_history.py \
  --history-root data/history \
  --norad 57754 \
  --source spacetrack \
  --start 2023-01-01 \
  --end 2026-12-31 \
  --output aditya_l1_history.json
```

## Space-Track 历史回溯

`.github/workflows/backfill-history.yml` 只允许手动触发。输入起止时间、逗号分隔的 NORAD 编号，并输入 `ARCHIVE_ONCE` 确认。若 NORAD 留空，工作流会处理当前目录中的所有目标，数据量可能很大。

回溯应遵守以下规则：

- 优先按少量目标和月度区间分批运行；
- 已成功下载并写入历史库的区间不得反复查询；
- 大范围、多目标历史数据优先采用 Space-Track 推荐的年度归档包；
- `fingerprints.log` 会过滤重复元素集，但这不构成重复调用 API 的理由；
- 回溯失败时先检查工作流日志和已有分片，再决定是否重试。

## 人工复核项目

自动更新后至少检查：

- 记录总数及新增、删除数量是否异常；
- NORAD 和 COSPAR 是否发生冲突；
- `H` 型或其他非标准元素是否被普通 TLE 解析器处理；
- 历元是否倒退或明显陈旧；
- 半长轴是否跨越 42,164 km 筛选边界；
- 任务状态是否被错误地从 `DECAY_DATE` 推断；
- Bill Gray 新候选是否具有可靠公开身份。

## 异常处理

- Space-Track Secrets 缺失：保留现有 Space-Track 快照，只更新可访问的数据。
- Space-Track 登录或查询失败：工作流失败，不覆盖上一次有效目录。
- Bill Gray 文件缺失：保留记录并标记 `source_file_missing`。
- 没有可解析元素：保留记录并标记 `no_parseable_element_set`。
- JSON 唯一键或来源重复：校验失败，停止部署。
- 历史分片哈希、记录数或指纹不一致：校验失败，不提交历史库。

## 回滚

当前目录文件由 Git 管理。若自动更新产生异常，可在 GitHub 中回退对应的数据更新提交。历史分片是不可变记录，原则上不删除；发现错误时应追加更正说明。不得把 Space-Track 密码或会话信息纳入回滚文件。

