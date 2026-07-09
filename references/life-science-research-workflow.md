# life-science-research 插件桥接流程

V2.1 将 life-science-research 定位为外部科学数据库证据扩展层。插件用于补齐 PubMed/PMC/OpenAlex 之外的靶标、蛋白、通路、疾病关联、临床研究、遗传证据和公共数据库线索。

## 触发条件

life-science-research 采用保守触发机制。不要把触发条件设计成少量关键词白名单；面对未知检测项目时，宁可先生成 LSR 查询计划，再由人工确认是否豁免。

课题涉及以下任一内容时触发：

- 标志物、蛋白、基因或靶标；
- 疾病机制、通路、网络或组织表达；
- 临床试验、队列研究或公共数据库证据；
- 遗传关联、变异解释或人群差异。
- 完整 IVD 调研中的检测项目、检测试剂盒、定量/定性检测、免疫分析、POCT、体外诊断、临床用途或样本相关产品画像。

只有用户明确确认“本次仅做注册/竞品/标准，不做科学数据库证据”时，才允许记录豁免，例如 `life_science_required=false` 或 `life_science_scope=只做注册/竞品/标准`。豁免必须保留在任务确认项中，不能由 agent 静默跳过。

## 执行顺序

1. 标准交付流水线先执行 LSR-first gate。需要 LSR 且尚未导入达标材料时，先停止通用采集并生成外部插件查询计划：

```bash
nuoyan life-science-plan --task-id <task_id> --json
```

2. 使用 `life-science-research:research-router-skill` 将问题拆成证据通道。
3. 按通道调用下游子 skill，例如 `uniprot-skill`、`string-skill`、`reactome-skill`、`opentargets-skill`、`clinicaltrials-skill`、`gwas-catalog-skill`、`clinvar-variation-skill`、`human-protein-atlas-skill`、`efo-ontology-skill`、`ncbi-pmc-skill`。
4. 默认覆盖目标：
   - 至少 12 条插件材料；
   - 至少 5 个来源数据库；
   - 至少 4 个证据通道，建议覆盖 target/protein、pathway/network、clinical、genetics/ontology。
5. 将结果整理为 JSON 列表，每条 finding 至少包含：
   - `source_database`
   - `evidence_lane`
   - `entity`
   - `query`
   - `result_summary`
   - `source_url`
   - `identifier`
6. 导入材料管线：

```bash
nuoyan import-life-science-findings --task-id <task_id> \
  --findings-json-file external_findings.json \
  --query "plasma p-tau217 Alzheimer disease" \
  --json
```

7. 后续继续运行：

```bash
nuoyan run-delivery-pipeline --task-id <task_id> --json
```

或在只重建交付物时运行：

```bash
nuoyan generate-evidence-cards --task-id <task_id> --json
nuoyan build-knowledge --task-id <task_id> --json
nuoyan export-review --task-id <task_id> --json
nuoyan build-standard-delivery --task-id <task_id> --json
nuoyan verify-package --task-id <task_id> --json
```

## 证据边界

- 插件结果必须进入 Material、SourceRun、EvidenceCard 和知识索引，不能只停留在对话摘要。
- 临床试验、遗传、通路和蛋白证据用于机制、合理性和补充线索，不得直接外推为 IVD 诊断性能证据。
- 每条导入结果必须保留来源库、查询式、实体、URL、采集时间和导入批次。
- `verify-package` 会检查 life-science-research 覆盖。标志物/机制类项目缺少插件导入或覆盖不足时，`scenario_coverage_ready=false`，`business_ready=false`。
