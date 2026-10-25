# /mock - Interactive Mock Interview

按一次一题的节奏进行：提问 → 用户回答 → 点评 → 必要时追问 → 下一题。交互期间只展示问题和必要澄清，不展示参考答案、评分规则或扣分点。

输入顺序：tracker → posting → 定向材料 →候选人公开材料 → 当前阶段 prep → 全局错题索引。领域明确匹配时加载 `.claude/domain-packs/<domain>/`，否则使用 `generic`，不猜领域。

固定 section 顺序：`evidence_verification`、`capability_expansion`、`transfer_scenarios`。问题池必须同时保存 JSON 和 Markdown 展示层，每题带 `source_evidence`。

最低收束条件：真实性核验至少 3 个高风险点，能力发散至少 3 项，迁移场景至少 1 个完整场景。过程状态由 `tools/mock_state.py` 保存，支持中断后恢复；答案和 rubric 只写状态文件，不在提问展示层渲染。

输出到申请工作区：`mock_<stage>_<date>.json` 与 `mock_<stage>_<date>.md`。
