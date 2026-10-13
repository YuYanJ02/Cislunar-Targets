# 数据字典与统一规则

## 数据层次

仓库保留四个层次的数据：

1. `data/registries/`：人工审查后的 Excel 登记表，是身份、范围和备注的可编辑来源。
2. `public/data/catalog.json`：供网页直接读取的统一目录，由脚本生成。
3. `data/history/`：只追加、不覆盖的历史根数分片、清单和去重索引。
4. Space-Track 和 Bill Gray 的在线源数据：由 GitHub Actions 定期获取，不在源码中保存认证信息。

## 历史记录字段

`data/history/shards/YYYY/MM/*.jsonl.gz` 中每行是一条独立历史记录：

| 字段 | 含义 |
| --- | --- |
| `schema_version` | 历史记录模式版本 |
| `recorded_at_utc` | 本仓库获取或归档该记录的时间 |
| `target_key` | 与当前目录一致的统一目标键 |
| `name`、`norad_cat_id`、`cospar_id` | 归档时的目标身份信息 |
| `source` | `spacetrack` 或 `bill_gray` |
| `source_url`、`source_commit`、`bill_gray_file` | 原始来源追溯信息 |
| `orbit` | 该历元的完整 OMM/TLE 轨道字段 |
| `fingerprint` | 去除验证时间后，对来源、目标和轨道内容计算的 SHA-256 |

`manifest.json` 记录各分片的路径、记录数、来源计数、历元范围、压缩前后大小和 SHA-256；`fingerprints.log` 是只追加的全局去重索引。历史分片生成后不得编辑或覆盖，如需修正，应追加更正记录并在文档中说明。

## 目标级字段

| 字段 | 含义 | 规则 |
| --- | --- | --- |
| `key` | 统一目标键 | 优先采用 `NORAD:<编号>`，其次采用 `COSPAR:<编号>` |
| `name` | 页面显示名称 | 优先采用经人工登记的 Bill Gray 名称，否则采用 Space-Track 名称 |
| `norad_cat_id` | NORAD 目录号 | 作为文本保存，避免未来编号格式变化 |
| `cospar_id` | 国际编号 | 采用 `YYYY-NNNAAA` 形式，未知时为空 |
| `aliases` | 其他名称 | 用于搜索，不替代稳定目标键 |
| `object_type` | 对象类型 | 当前筛选范围为航天器/PAYLOAD |
| `orbit_regime` | 轨道区域 | 当前登记统一标为 `XGEO`，表示半长轴超过 GEO 阈值 |
| `identity_status` | 身份可信度 | `confirmed`、`probable` 或 `unknown` |
| `mission_status` | 任务状态 | 默认 `unknown`，不得由未再入状态推断“正常运行” |
| `eligible` | 是否满足当前筛选口径 | 任一来源满足时为 `true` |
| `sources` | 来源记录数组 | 每个目标最多各有一个 Space-Track 和 Bill Gray 当前记录 |

## 来源级字段

每个 `sources[]` 元素表示一个数据来源的当前记录。

| 字段 | 含义 |
| --- | --- |
| `source` | `spacetrack` 或 `bill_gray` |
| `last_verified_utc` | 本仓库最后一次验证该来源的时间 |
| `source_url` | 可审计的源页面或 API 查询地址 |
| `source_commit` | Bill Gray 仓库提交版本 |
| `bill_gray_file` | Bill Gray 根目录中的源文件名 |
| `catalog_id` | 来源目录中的目标编号 |
| `update_status` | 自动更新结果或异常原因 |
| `orbit` | 当前轨道信息 |

## 轨道字段

| 字段 | 单位 | 说明 |
| --- | --- | --- |
| `epoch_utc` | UTC | 元素集历元 |
| `semi_major_axis_km` | km | 半长轴；不是目标瞬时地心距离 |
| `period_days` | day | 轨道周期 |
| `eccentricity` | 1 | 偏心率 |
| `inclination_deg` | deg | 轨道倾角 |
| `raan_deg` | deg | 升交点赤经 |
| `arg_pericenter_deg` | deg | 近地点幅角 |
| `mean_anomaly_deg` | deg | 平近点角 |
| `mean_motion_rev_day` | rev/day | 平均运动 |
| `mean_motion_dot` | rev/day² | 平均运动一阶导数 |
| `mean_motion_ddot` | rev/day³ | 平均运动二阶导数 |
| `bstar` | 1/Earth radii | SGP4 BSTAR 阻力项 |
| `element_set_no` | — | 元素集编号 |
| `rev_at_epoch` | rev | 历元时圈次 |
| `perigee_altitude_km` | km | 近地点高度 |
| `apogee_altitude_km` | km | 远地点高度 |
| `ephemeris_type` | — | TLE 历表类型；`H` 为 Bill Gray 扩展状态向量 |
| `center_name` | — | OMM 中心天体 |
| `ref_frame` | — | OMM 参考系 |
| `time_system` | — | OMM 时间系统 |
| `mean_element_theory` | — | 平均根数理论，例如 SGP4 |
| `ccsds_omm_version` | — | CCSDS OMM 版本 |
| `creation_date_utc` | UTC | Space-Track 产品生成时间 |
| `originator` | — | 产品发布机构 |
| `gp_id` | — | Space-Track GP 产品编号 |
| `tle_line0/1/2` | — | 当前原始名称行和元素行 |

缺失数值必须保存为 `null`，页面显示为“—”，不能以 0 代替。

## 当前筛选口径

Space-Track 当前目录采用：

```text
OBJECT_TYPE = PAYLOAD
LAUNCH_DATE > 2000-12-31
DECAY_DATE = null
SEMIMAJOR_AXIS > 42164 km
```

这组条件表示“2000年以后发射、目录类型为载荷、未记录再入、半长轴超过 GEO”。它不能证明目标仍在正常工作，也不能证明目标始终位于 GEO 半径之外。

## 双源合并

- NORAD 相同：直接视为同一目标。
- NORAD 缺失但 COSPAR 相同：可合并，但应保留身份可信度。
- 两者都缺失：保持为独立目标，等待人工审查。
- 来源轨道不互相覆盖。网页分别展示两个来源，并计算差值。

