```python
import re

class MemoryParsingService:
    def __init__(self):
        self.STRONG_FACT_PATTERNS = [
            # Specific structures already mapped to correct confidence scores
            r"\b(is|are|was|were)\b(?!(\s*(not|n't|no|never)\b))",
            # Other strong fact patterns...
        ]
        self.AUXILIARY_VERBS = ["is", "are", "was", "were"]

    def parse_memory(self, sentence):
        # Check for ambiguity
        if self.is_ambiguous(sentence):
            return "Ambiguous sentence"

        # Classify sentence
        classification = self.classify_sentence(sentence)
        return classification

    def is_ambiguous(self, sentence):
        # Check if sentence contains standalone auxiliary verbs
        for verb in self.AUXILIARY_VERBS:
            if re.search(rf"\b{verb}\b", sentence) and not self.is_part_of_strong_pattern(sentence, verb):
                return True

        return False

    def is_part_of_strong_pattern(self, sentence, verb):
        # Check if auxiliary verb is part of a strong fact pattern
        for pattern in self.STRONG_FACT_PATTERNS:
            if re.search(pattern, sentence):
                return True

        return False

    def classify_sentence(self, sentence):
        # Classify sentence based on strong fact patterns
        for pattern in self.STRONG_FACT_PATTERNS:
            if re.search(pattern, sentence):
                return "Fact"

        return "Unknown"

def main():
    service = MemoryParsingService()
    sentences = [
        "The sky is blue.",
        "The dog is running.",
        "The cat was sleeping.",
        "The baby was crying.",
        "Is the door open?",
        "Are you going to the store?",
        "Was the book interesting?",
        "Were the flowers beautiful?"
    ]

    for sentence in sentences:
        print(f"Sentence: {sentence}, Classification: {service.parse_memory(sentence)}")

if __name__ == "__main__":
    main()
```