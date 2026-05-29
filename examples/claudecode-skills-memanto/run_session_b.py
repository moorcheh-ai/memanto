from __future__ import annotations

from memanto_skills import build_backend, pre_skill_context


def main() -> None:
    """Demonstrate pre-skill context retrieval for Session B."""

    try:
        backend = build_backend()
        context = pre_skill_context(
            backend=backend,
            skill="/tdd",
            prompt="Add tests for Stripe webhook retries.",
            path_hint="services/payments",
        )
    except Exception as error:
        raise RuntimeError(f"Session B failed to retrieve context: {error}") from error

    print("Session B injected context:")
    print(context or "No relevant engineering memory found.")


if __name__ == "__main__":
    main()
