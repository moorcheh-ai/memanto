from __future__ import annotations

from memanto_skills import build_backend, post_skill_capture


def main() -> None:
    """Demonstrate post-skill memory capture for Session A."""

    try:
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
    except Exception as error:
        raise RuntimeError(f"Session A failed to store memory: {error}") from error

    print("Session A stored memory:")
    print(f"- {memory.title}: {memory.content}")


if __name__ == "__main__":
    main()
