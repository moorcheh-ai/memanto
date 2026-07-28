# Python Design Patterns Deep Dive

**Type:** auto-classified
**Source:** claude
**Confidence:** 0.8
**Tags:** claude, ai-conversation
**Created:** 2025-11-15 10:00:00+00:00

---

[User message 1]: Can you explain the Strategy pattern in Python with a real-world example? I want to understand when to use it versus simple functions.

[Assistant message 2]: The Strategy pattern is ideal when you have multiple interchangeable algorithms. A real-world example is a payment processing system:

```python
from abc import ABC, abstractmethod

class PaymentStrategy(ABC):
    @abstractmethod
    def pay(self, amount: float) -> bool: pass

class CreditCardPayment(PaymentStrategy):
    def __init__(self, card_number: str):
        self.card_number = card_number
    def pay(self, amount: float) -> bool:
        print(f'Charging {amount} to card {self.card_number[-4:]}')
        return True

class PayPalPayment(PaymentStrategy):
    def __init__(self, email: str):
        self.email = email
    def pay(self, amount: float) -> bool:
        print(f'PayPal charge of {amount} to {self.email}')
        return True

class Order:
    def __init__(self, strategy: PaymentStrategy):
        self.strategy = strategy
    def checkout(self, total: float) -> bool:
        return self.strategy.pay(total)
```

Use Strategy when: (1) you need runtime algorithm switching, (2) the logic is complex enough to warrant a class, (3) you want to follow Open/Closed principle.

[User message 3]: What about the Observer pattern? When would I use that in a backend system?

[Assistant message 4]: Observer is perfect for event-driven backend systems. Use it when you need one-to-many notifications without tight coupling.

Common backend scenarios:
- **Audit logging**: When an order is placed, notify the audit service, analytics service, and notification service
- **Cache invalidation**: When data changes, notify all cache layers
- **WebSocket broadcasts**: Push updates to connected clients

In practice, most Python backends use message queues (Redis, RabbitMQ) instead of in-process Observer, but the pattern is the same conceptually.

---
*Migration metadata:*
**Source:** claude:conversation
**Claude title:** Python Design Patterns Deep Dive
**Claude UUID:** conv_claude_001
**Message count:** 4
**Source created_at:** 2025-11-15T10:00:00+00:00
