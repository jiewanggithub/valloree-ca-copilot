# Vallorée CA Copilot

为奢侈品 Client Advisor（CA）生成 **3 条符合品牌调性的中文微信话术**，覆盖 6 个场景：问候、推荐、售后、唤醒、活动邀约、价格异议。
品牌 *Maison Vallorée（瓦洛蕾）* 是虚构的日内瓦高级珠宝与腕表品牌。所有客户、产品和对话均为虚构。

[English README](README.md)

## 提交文件在哪里看

| Brief 要求 | 文件 |
|---|---|
| 报告（A 工作日志 · B 方法论 · D 评估 · E 缺陷与下一步 · 架构图） | `deliverables/Valloree_CA_Copilot_report.pdf`（HTML 源文件：`docs/report.html`） |
| C. 50 个测试用例及输出 | `deliverables/test_cases_v3.xlsx`：C 表为用例和输出；D 表为每条话术的评分；E 表为 v1 / v2 / v3 对比 |
| 工作日志里的 prompt 截图 | `docs/screenshots/1.png` … `10.png`（报告 A 节也有） |
| 架构图 | `docs/architecture.svg`（报告 B2 节也有） |
| 可运行的工具 | `ca_copilot/`（核心逻辑），`server.py` + `frontend/`（Web 应用）；用 `./start.sh` 启动 |
| 原始输出、judge 评分、人工复核标签 | `results/v1`–`v3`，`data/human_review_v*.yaml` |

> 报告为英文（按 brief 要求），本 README 只是中文导读。

## 快速开始

```bash
conda env create -f environment.yml      # 创建 conda 环境 "ca-copilot"
conda activate ca-copilot
cp .env.example .env                     # 填入 DEEPSEEK_API_KEY（如用 Qwen 作 judge，可再填 DASHSCOPE_API_KEY）
./start.sh                               # Web 应用 -> http://localhost:8000
```

Web 应用有两个页面：
- **生成**：选择场景和客户，编辑微信聊天记录和产品，生成 3 条话术。每条话术显示它引用的事实编号、合规标记和 fact-check
  删掉的内容，并提供“复制”和“放入对话预览”按钮。如果现在发送会违反客户偏好（例如时间），会显示提醒。
- **测试集评估**：50 个测试用例的 v1 / v2 / v3 输出并排对比，附人工复核结论和 judge 评分。读取已保存的结果，不调用 API。

`streamlit run app.py` 是早期的简易 demo，仍可运行。

在 Python 里用新的输入运行：

```python
from ca_copilot.data import load_clients, load_products
from ca_copilot.pipeline import Generator
from ca_copilot.schema import Request, Turn

clients, products = load_clients(), load_products()
req = Request(scenario="price_objection", today="2026-11-20", client=clients["C03"],
              history=[Turn(speaker="client", time="2026-11-20 10:00", text="能便宜一点吗？")],
              products=[products["LRR-B-01"]])
for c in Generator().generate(req).candidates:
    print(c.angle, c.message, c.issues)
```

## 评估

```bash
python scripts/run_eval.py --version v3            # 生成并评分全部 50 个用例 -> results/v3/
python scripts/run_eval.py --version v3 --rejudge  # 用当前 judge 重新给已有输出打分
python scripts/build_report.py v1 v2 v3            # 计算指标，生成 deliverables/test_cases_v3.xlsx
python scripts/make_charts.py && python scripts/build_docs.py   # 生成图表和报告 HTML/PDF
python -m pytest -q tests                          # 规则检查（guardrail）回归测试
```

注意：`docs/report.html` 由 `scripts/build_docs.py` 生成，要改报告内容请改这个脚本，不要直接改 HTML。

## 目录结构

| 路径 | 内容 |
|---|---|
| `brand/` | 品牌手册（假设、调性、合规规则）和产品目录 |
| `data/clients.yaml`, `data/cases.yaml` | 20 个 CRM 客户画像，50 个测试用例（每个注明测什么） |
| `data/human_review_v*.yaml` | 各版本的人工复核标签（OK / EDIT / UNACCEPTABLE + 缺陷代码） |
| `ca_copilot/context.py` | 由代码确定性计算的信号、客户偏好规则、编号事实清单 |
| `ca_copilot/scenarios.py`, `prompts.py` | 场景 playbook（每个场景 3 个角度）、prompt、fact-check prompt |
| `ca_copilot/pipeline.py` | 生成 → fact-check → 规则检查 → 修复 |
| `ca_copilot/guardrails.py` | 规则检查（折扣、广告法绝对化用语、投资承诺、编造价格/新品、政策滥用等） |
| `server.py`, `frontend/` | FastAPI 后端 + 单页 Web 应用（无需构建） |
| `ca_copilot/judge.py` | LLM judge：6 个维度的评分标准 + hard fail，先做事实核查 |
| `snapshots/` | v1、v2、v3 的冻结代码（每个结果文件都记录了来自哪个版本） |
| `results/` | 各版本的原始输出和 judge 评分；`_judge_calibration/` 是早期 judge 的校准记录 |
| `docs/` | 报告源文件、架构图、图表、prompt 截图 |

## 配置

| 变量 | 默认值 | 说明 |
|---|---|---|
| `GEN_PROVIDER` / `JUDGE_PROVIDER` | `deepseek` / `qwen` | `deepseek` 或 `qwen`（任意 OpenAI 兼容接口） |
| `DEEPSEEK_MODEL`, `QWEN_MODEL` | `deepseek-chat`, `qwen-plus` | |
