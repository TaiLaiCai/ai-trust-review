# S1 补证包 · 第二批(addendum)入库候选

组装:tlc(Claude Code + GLM,子代理×2 + 终验);合流生产方:apo;复跑:Hark(绑定本 PR 最终 head 后执行);独立审阅:Grok(已出首审 6719068889,本批为其差额项的回应)。**本目录不主张 S1 闭合。**

- `A2-originals/`(16)+ manifest(去私有路径版):T1–T6/TP/PREFLIGHT-LOCAL 全部原始输出,逐字节同私有库原件(脱敏 0 命中);Hark 已按包复跑 16/16 REPRODUCED。
- `replay-kit/`(7 件,含 alt-inputs)+ manifest:revision2 源码与输入,字节与 11-02 历史登记一致;**status_input.json 暂缓**——主人 A 裁定在案(#6 6719172659),正文公开待 apo 明确授权后另行补入。
- 三件脱敏件 + `hash-mappings.json`(均去私有路径版,源件/入库件双 SHA 见 merge-manifest):核原件一律用映射内 original_sha256,不用脱敏字节。
- `B-originals-hashlist.txt`:B 底层原件当前哈希(B4 纪律:不含自身,整体摘要 `d4eafc8d…` 另记于 merge-manifest;旧 CONFLICT 保留;不倒填)。
- `d3-summary.md`:D3 检索哈希+脱敏摘要(全文不入库;「检索未找到记录 ≠ 证明没有安装/外发」)。
- 排除未入:`authorized-only/`(vault-manifest、verify.sh)、d3 全文——主人裁定 1/2。

主人的原库实测(2026-11-08 15:5x,退出 0,范围 522)与 Hark 两张回执见 #6。
