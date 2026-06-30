# life-science-research 插件桥接流程

V2.1 将 life-science-research 定位为外部科学数据库证据扩展层。插件用于补齐 PubMed/PMC/OpenAlex 之外的靶标、蛋白、通路、疾病关联、临床研究、遗传证据和公共数据库线索。

## 触发条件

课题涉及以下任一内容时触发：

- 标志物、蛋白、基因或靶标；
- 疾病机制、通路、网络或组织表达；
- 临床试验、队列研究或公共数据库证据；
- 遗传关联、变异解释或人群差异。

## 执行顺序

1. 使用 `life-science-research:research-router-skill` 将问题拆成 1-3 个证据通道。
2. 按通道调用下游子 skill，例如 `uniprot-skill`、`string-skill`、`reactome-skill`、`opentargets-skill`、`clinicaltrials-skill`、`gwas-catalog-skill`、`clinvar-variation-skill`、`ncbi-pmc-skill`。
3. 将结果整理为 JSON 列表，每条 finding 至少包含：
   - `source_database`
   - `evidence_lane`
   - `entity`
   - `query`
   - `result_summary`
   - `source_url`
   - `identifier`
4. 导入材料管线：

```bash
nuoyan import-life-science-findings --task-id <task_id> \
  --findings-json-file external_findings.json \
  --query "plasma p-tau217 Alzheimer disease" \
  --json
```

5. 后续继续运行：

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
