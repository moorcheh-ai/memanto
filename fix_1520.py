import re

class AmbiguityGuard:
    def __init__(self):
        self.AUXILIARY_VERBS = ["is", "are", "was", "were"]
        # Require a subject-verb-object structure to be considered a strong fact
        self.STRONG_FACT_PATTERNS = [
            r"\b\w+\s+(is|are|was|were)\s+\w+\b" 
        ]

    def parse_memory(self, record):
        # Handle MemoryRecord object or string
        if hasattr(record, 'text'):
            sentence = record.text
        else:
            sentence = str(record)

        if self.is_ambiguous(sentence):
            if hasattr(record, 'type'):
                record.type = "Ambiguous"
                return record
            return "Ambiguous sentence"

        classification = self.classify_sentence(sentence)
        if hasattr(record, 'type'):
            record.type = "fact" if classification == "Unknown" else classification.lower()
            return record
        return classification

    def is_ambiguous(self, sentence):
        for verb in self.AUXILIARY_VERBS:
            # Case-insensitive search
            if re.search(rf"\b{verb}\b", sentence, flags=re.IGNORECASE):
                if not self.is_part_of_strong_pattern(sentence, verb):
                    return True
        return False

    def is_part_of_strong_pattern(self, sentence, verb):
        for pattern in self.STRONG_FACT_PATTERNS:
            # Case-insensitive search
            if re.search(pattern, sentence, flags=re.IGNORECASE):
                return True
        return False

    def classify_sentence(self, sentence):
        if not self.is_ambiguous(sentence):
            return "Fact"
        return "Unknown"
