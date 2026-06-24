import os
import sys
import logging
from memanto.agent import MemantoAgent
from memanto.config import load_config

# Configure basic logging for the CLI
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

def _validate_environment():
    """
    Ensure that all required environment variables are present.
    Currently, the Memanto CLI requires the MOORCHEH_API_KEY to be set.
    """
    api_key = os.getenv("MOORCHEH_API_KEY")
    if not api_key:
        logging.error(
            "Missing required environment variable: MOORCHEH_API_KEY.\n"
            "Please set it in your environment or in a .env file before running the CLI.\n"
            "Example:\n"
            "  export MOORCHEH_API_KEY=mk_your_api_key_here\n"
            "or use a .env file with the variable defined."
        )
        sys.exit(1)
    return api_key

def main():
    """
    Entry point for the Memanto CLI.
    """
    # Validate required environment variables
    api_key = _validate_environment()

    # Load configuration (can be overridden by CLI args in the future)
    config = load_config()

    # Initialize the Memanto agent with the validated API key
    agent = MemantoAgent(api_key=api_key, config=config)

    # Simple interactive loop for demonstration purposes
    logging.info("Memanto CLI started. Type 'exit' to quit.")
    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            logging.info("\nExiting Memanto CLI.")
            break

        if user_input.lower() in {"exit", "quit"}:
            logging.info("Exiting Memanto CLI.")
            break

        if not user_input:
            continue

        try:
            response = agent.process(user_input)
            print(response)
        except Exception as e:
            logging.exception("An error occurred while processing the input: %s", e)
            print("Error:", e)

if __name__ == "__main__":
    main()