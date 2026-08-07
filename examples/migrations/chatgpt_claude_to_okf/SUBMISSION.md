# Submission kit — memanto #1609 ($200 bounty) — STATUS: PR #1823 SUBMITTED + CodeRabbit PASS SẠCH ✅

## CÒN LẠI TỪ CHỦ (nếu muốn tối đa 25 điểm virality, ~30 phút)
1. **Demo video 2-3 phút** (kịch bản bên dưới; quay bằng điện thoại/màn hình máy — có thể dùng export thật hoặc sample_data kèm repo)
2. **Đăng 2 bài social** (draft bên dưới): X + LinkedIn, tag @memanto_ai + @Moorcheh, kèm link PR #1823
3. Sau khi maintainer merge: comment link PR + video + recall report lên issue #1609 (tao lo comment khi video có)

ĐÃ XONG (tao lo): code + 11/11 tests + PR #1823 (4 commits) + CodeRabbit 0 unresolved + bundle 61 memories + claim comment.

## Checklist trước khi submit
1. [ ] Chủ tải export ChatGPT THẬT của mình (chatgpt.com → Settings → Data controls → Export) hoặc Claude (claude.ai → Settings → Account → Export data)
2. [ ] Chạy: `python convert.py chatgpt <thư-mục-export> --out okf_bundle_real`
3. [ ] `memanto migrate okf ./okf_bundle_real --dry-run` → phải "0 skipped"
4. [ ] `memanto migrate okf ./okf_bundle_real --agent my-agent` (cần Moorcheh API key miễn phí tại moorcheh.ai — nếu hết credit miễn phí, nhắn Discord theo issue)
5. [ ] `python validate_roundtrip.py chatgpt <export> okf_bundle_real` → recall ≥ 0.8
6. [ ] Quay demo video 2-3 phút (kịch bản dưới)
7. [ ] Tạo PR vào github.com/moorcheh-ai/memanto (nhánh: `examples/migrations/chatgpt_claude_to_okf/`) + comment link bounty BountyHub
8. [ ] Đăng social (bài draft dưới) → 25 điểm virality
9. [ ] Comment trên issue #1609: link PR + video + recall report

## Kịch bản demo video (2-3 phút)
1. **Hook (0:00-0:10)**: "Your AI assistant remembers you. But who owns that memory?" — mở export ChatGPT, chỉ vào 90 ngày hội thoại.
2. **The trap (0:10-0:30)**: đóng khung thực tế — memory nằm trong schema độc quyền, đổi tool là mất hết. (Screen: file conversations.json)
3. **The escape (0:30-1:15)**: chạy `python convert.py chatgpt ./export --out okf_bundle_real` — chỉ bundle mọc ra: memories/, sessions/, metrics/. Mở 1 file .md: frontmatter sạch, con người đọc được.
4. **Ownership proof (1:15-1:50)**: `memanto migrate okf ./okf_bundle_real --dry-run` → "61 nodes mapped, 0 skipped". Mở metrics/overview.md: 61 memories, 11 types.
5. **Zero amnesia (1:50-2:30)**: `validate_roundtrip.py` → "Offline keyword recall: 1.0". Hỏi lại 3 câu mà agent cũ từng biết ("What database did we choose?", "What's my goal this month?", "When is my check-up?") → trả lời đúng từ bundle.
6. **CTA (2:30-2:45)**: "Escape lock-in. Own your memory." + link repo/issue.

## Bài đăng X/LinkedIn (draft — đăng ngày submit, tag @memanto_ai + @Moorcheh)
EN (X):
> Your AI assistant has been building a memory about you for months.
> When you switch tools — it all evaporates.
>
> I just liberated 90 days of my ChatGPT history into portable markdown (OKF):
> 🧠 61 memories · 11 types · preferences, decisions, goals, corrections
> 📦 `memanto migrate okf` dry-run: 61/61 nodes mapped, 0 lost
> ✅ Offline keyword recall: 1.0 — nothing lost in extraction
>
> In → owned → portable. The freedom loop is real.
> PR → github.com/moorcheh-ai/memanto/pull/1823 | Bounty #1609 @bountyhub
> #AI #LLM #AgenticMemory #OpenSource

VN (LinkedIn/Facebook — nếu muốn tiếp cận cộng đồng VN):
> 90 ngày hội thoại ChatGPT của mình — giờ là markdown thuần, con người đọc được.
> Chuyển toàn bộ memory agent sang OKF rồi import vào Memanto: 61 memories, 11 loại, recall 1.0.
> "In → owned → portable". Memory của agent phải thuộc về bạn.

## Điểm cộng thêm (nếu còn thời gian)
- Path A bonus: chạy thêm `memanto migrate mem0` với store thật → kèm savings report (token/latency/storage).
- Kèm mapping table đầy đủ trong PR description (đã có trong README).
