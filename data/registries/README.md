# Excel 登记表

本目录保存建立网页目录时使用的人工审查登记表：

- `地月空间目标登记表_SpaceTrack.xlsx`
- `地月空间目标登记表_BillGray.xlsx`
- `地月空间目标登记表模板.xlsx`

Excel 文件用于人工复核、批量编辑和离线归档。网页运行时读取的是 `public/data/catalog.json`。

GitHub Actions 自动更新 JSON 中的当前轨道信息，不自动覆盖 Excel 人工登记表。身份状态、任务状态、备注和人工判断应先在 Excel 中审查，然后运行：

```bash
python scripts/import_registry.py \
  --bill-gray-xlsx data/registries/地月空间目标登记表_BillGray.xlsx \
  --space-track-xlsx data/registries/地月空间目标登记表_SpaceTrack.xlsx \
  --output public/data/catalog.json
```

导入前请保留一份历史版本。不要仅凭 `DECAY_DATE` 为空将任务状态填写为“正常运行”。

