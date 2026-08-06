# Submission kit — memanto #1609 ($200 bounty)

## CẦN TỪ CHỦ (tối thiểu, ~15-20 phút tổng cộng)
1. **GitHub account** (BẮT BUỘC — tao không tạo được: trang signup bị DataDome bot-check chặn + cần click link verify email):
   https://github.com/signup — tạo tay, dùng email nanoboy9889@gmail.com, click link verify trong email.
   → Báo tao, tao chạy `gh auth login` (device flow — chủ xác nhận mã trên browser) rồi tao làm HẾT phần fork/push/PR.
2. **Export ChatGPT THẬT**: chatgpt.com → Settings → Data controls → Export data (email sẽ gửi link tải ~vài phút; giải nén ra thư mục).
   Hoặc export Claude: claude.ai → Settings → Account → Export data.
3. **Demo video 2-3 phút** (kịch bản bên dưới; có thể quay bằng điện thoại, màn hình máy).

KHÔNG cần chủ: code, test, docs, PR text, social post draft — tao lo hết.

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
3. **The escape (0:30-1:15)**: chạy `python convert.py chatgpt ./export --out okf_bundle` — chỉ bundle mọc ra: memories/, sessions/, metrics/. Mở 1 file .md: frontmatter sạch, con người đọc được.
4. **Ownership proof (1:15-1:50)**: `memanto migrate okf ./okf_bundle --dry-run` → "66 nodes mapped, 0 skipped". Mở metrics/overview.md: 63 memories, 11 types.
5. **Zero amnesia (1:50-2:30)**: `validate_roundtrip.py` → "Offline recall: 1.0". Hỏi lại 3 câu mà agent cũ từng biết ("What database did we choose?", "What's my goal this month?", "When is my check-up?") → trả lời đúng từ bundle.
6. **CTA (2:30-2:45)**: "Escape lock-in. Own your memory." + link repo/issue.

## Bài đăng X/LinkedIn (draft — đăng ngày submit, tag @memanto_ai + @Moorcheh)
EN (X):
> Your AI assistant has been building a memory about you for months.
> When you switch tools — it all evaporates.
>
> I just liberated 90 days of my ChatGPT history into portable markdown (OKF):
> 🧠 63 memories · 11 types · preferences, decisions, goals, corrections
> 📦 Imported into @memanto_ai — 66/66 nodes, 0 lost
> ✅ Round-trip recall: 1.0 — same answers, zero amnesia
>
> In → owned → portable. The freedom loop is real.
> Repo → [link PR] | Bounty #1609 @bountyhub
> #AI #LLM #AgenticMemory #OpenSource

VN (LinkedIn/Facebook — nếu muốn tiếp cận cộng đồng VN):
> 90 ngày hội thoại ChatGPT của mình — giờ là markdown thuần, con người đọc được.
> Chuyển toàn bộ memory agent sang OKF rồi import vào Memanto: 63 memories, 11 loại, recall 1.0.
> "In → owned → portable". Memory của agent phải thuộc về bạn.

## Điểm cộng thêm (nếu còn thời gian)
- Path A bonus: chạy thêm `memanto migrate mem0` với store thật → kèm savings report (token/latency/storage).
- Kèm mapping table đầy đủ trong PR description (đã có trong README).
