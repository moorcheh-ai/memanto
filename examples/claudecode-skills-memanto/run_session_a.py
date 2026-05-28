from __future__ import annotations

from memanto_skills import build_backend, post_skill_capture


def main() -> None:
    backend = build_backend()
    memory = post_skill_capture(
        backend=backend,
        skill="/grill-with-docs",
        prompt="Review the payments service architecture.",
        transcript=(
            "Decision: use a repository layer for Stripe webhook persistence. "
            "Keep webhook signature verification at the HTTP boundary and store "
            "only normalized event records under services/payments."
        ),
        path_hint="services/payments",
    )
    print("Session A stored memory:")
    print(f"- {memory.title}: {memory.content}")


if __name__ == "__main__":
    main()
