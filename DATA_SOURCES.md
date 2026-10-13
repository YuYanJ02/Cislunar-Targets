# 数据来源、引用与许可边界

本文件说明“地月空间目标目录”所使用的原始数据、筛选口径、推荐引用方式和再发布注意事项。它不是对原始数据版权或许可状态的替代解释；若用于正式出版、商业产品或大规模再分发，应同时核对来源方的最新条款。

## 1. Space-Track.org

### 来源与产品

- 来源网站：<https://www.space-track.org/>
- 官方 API 与数据说明：<https://www.space-track.org/documentation>
- 本项目当前自动获取的数据产品：`class/gp`，以 JSON 返回最新 GP/OMM 字段。
- 数据提供与维护机构：United States Space Command（USSPACECOM）/ 18th Space Defense Squadron（18 SDS；以 Space-Track 当前说明为准）。

Space-Track 官方文档的“Redistribution of Basic SSA Information”条款说明：通过 Space-Track 获取的基本 SSA 数据及其派生分析可以转发或再发布，但必须给予适当引用。基本 SSA 数据包括 TLE/OMM、SATCAT 以及衰减和再入数据。使用者仍应遵守账户协议、API 频率限制和 Space-Track 的最新规则。

### 本项目的自动查询口径

```text
https://www.space-track.org/basicspacedata/query/class/gp/OBJECT_TYPE/PAYLOAD/LAUNCH_DATE/%3E2000-12-31/DECAY_DATE/null-val/SEMIMAJOR_AXIS/%3E42164/orderby/NORAD_CAT_ID/format/json
```

对应条件为：

- `OBJECT_TYPE = PAYLOAD`
- `LAUNCH_DATE > 2000-12-31`
- `DECAY_DATE = null`
- `SEMIMAJOR_AXIS > 42164 km`

注意：`DECAY_DATE = null` 仅表示目录中没有再入日期，不证明航天器仍在正常运行；半长轴大于 GEO 也不等于目标在所有时刻都位于 GEO 高度之外。

### 推荐引用

论文或报告中可按所用格式调整为：

> Space-Track.org. General Perturbations (GP) / Orbit Mean-Elements Message (OMM) basic SSA data, U.S. Space Command, accessed YYYY-MM-DD. https://www.space-track.org/

若结果来自某次固定导出，应同时记录查询 URL、访问日期、目录生成时间和每条记录的 `epoch_utc`。本项目记录中的 `source_url`、`retrieved_at_utc` 或 `last_verified_utc` 字段可用于复现引用。

历史库从每日 `GP` 快照持续积累，不能保证包含两个抓取时刻之间发布的每个元素集。通过 `GP_HISTORY` 补齐的分片会保留实际查询区间和获取时间；历史产品按 Space-Track 的 API 指南下载后在本仓库中留存，不重复抓取同一区间。

## 2. Bill Gray 高轨目标根数

### 来源与数据特点

- GitHub 仓库：<https://github.com/Bill-Gray/tles>
- 项目说明页：<https://www.projectpluto.com/tles/tles.htm>
- 维护者：Bill Gray

仓库包含 Bill Gray 为高轨人造目标计算或拟合的 TLE。其 README 说明，这些根数由 Find_Orb 计算轨道和星历后，再使用 `eph2tle` 进行最小二乘拟合；其中部分高轨记录使用特殊的 ephemeris type，不能假定所有软件都能按普通 TLE 正确处理。

### 可追溯性与许可提醒

本项目对 Bill Gray 来源尽量保留：

- 原始仓库 URL；
- `.tle` 源文件名；
- 对应 Git 提交 SHA；
- 获取或核验时间；
- 原始 TLE/H 型状态向量文本。

截至 2026-10-13，`Bill-Gray/tles` 仓库根目录没有声明适用于整库内容的 `LICENSE`。因此，公开可访问不应被解释为授予任意复制、修改或再许可权。研究引用时至少保留作者、仓库、具体源文件、提交 SHA 和访问日期；若要将其数据大规模再分发、用于商业服务或采用新的数据许可证，建议先向维护者确认授权范围。

### 推荐引用

> Gray, Bill. *TLEs for high-altitude artificial satellites*. GitHub repository, file `<源文件名>`, commit `<提交 SHA>`, accessed YYYY-MM-DD. https://github.com/Bill-Gray/tles

## 3. 本项目的派生目录

本仓库将两个来源的数据规范化为统一字段，并根据标识符进行目录级匹配、筛选和展示。该处理可能包括格式转换、字段重命名、单位统一、轨道摘要计算和源间差异计算；它不会把两个来源的接近程度解释为绝对轨道精度。

推荐同时引用本项目：

> YuYanJ02. *Cislunar Targets: 地月空间目标目录*. GitHub repository, commit `<提交 SHA或版本>`, accessed YYYY-MM-DD. https://github.com/YuYanJ02/Cislunar-Targets

仓库根目录的 `CITATION.cff` 可被 GitHub、“Cite this repository”和常用文献管理工具读取。为保证结果可复现，建议在论文或报告中同时给出：

1. 本项目提交 SHA；
2. 目录生成时间；
3. 实际使用的源数据历元；
4. Space-Track 查询条件；
5. Bill Gray 的源文件和提交 SHA。

## 4. 许可边界与使用限制

- 本项目自编代码、页面和说明文档，与第三方原始数据是不同的权利对象。
- 仓库将来选择的软件许可证时，该许可证不会自动覆盖 Space-Track 或 Bill Gray 的第三方数据。
- Space-Track 数据的转发与分析引用应遵守其官方文档、账户协议和 API 使用规则。
- Bill Gray 数据按上述来源和提交进行归属；在来源方未明确整库许可证的情况下，不对其另行授权。
- 本目录不代表 Space-Track、USSPACECOM、18 SDS 或 Bill Gray 对本项目的认可。
- 数据仅供目录维护、研究和方法验证，不用于业务级碰撞预警、航天器操作或安全关键决策。
- 数据可能存在遗漏、误标识、历元陈旧、拟合误差或源间差异；使用者应结合精密星历、测控数据或其他独立参考进行验证。

如发现来源、标识或引用信息有误，请通过本仓库的 [Issues](https://github.com/YuYanJ02/Cislunar-Targets/issues) 提交可核验依据。

