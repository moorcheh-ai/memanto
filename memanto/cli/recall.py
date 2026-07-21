import argparse
import datetime

from memanto.memory.retrieval import Retrieval

def parse_args():
    parser = argparse.ArgumentParser(description="Recall memories from MEMANTO.")
    # ... existing arguments ...

    parser.add_argument(
        "--as-of",
        type=str,
        help="Recall memories as of a specific time (e.g., 'yesterday', '2023-01-01')",
    )

    return parser.parse_args()

def main():
    args = parse_args()
    retrieval = Retrieval()

    if args.as_of == "yesterday":
        # Use end of yesterday for as-of parameter
        today = datetime.datetime.utcnow().date()
        yesterday = today - datetime.timedelta(days=1)
        end_of_yesterday = datetime.datetime.combine(yesterday, datetime.time.max)
        args.as_of = end_of_yesterday.isoformat()

    # ... rest of the function ...