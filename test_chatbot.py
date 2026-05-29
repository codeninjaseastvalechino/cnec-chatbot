#!/usr/bin/env python3
"""
Quick test of the chatbot without running the Flask server.

Usage:
    python3 test_chatbot.py
"""

from dotenv import load_dotenv
from pathlib import Path

# Load .env variables before importing chatbot
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

from chatbot import ChatbotEngine

def main():
    print("Initializing ChatbotEngine...")
    chatbot = ChatbotEngine()

    print("\n" + "=" * 60)
    print("CNEC Chatbot Test")
    print("=" * 60)
    print("\nType 'quit' to exit.\n")

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        if not user_input:
            continue

        try:
            print("\nClaude: ", end="", flush=True)
            response = chatbot.chat(user_input)
            print(response)
            print()
        except Exception as e:
            print(f"Error: {e}\n")


if __name__ == "__main__":
    main()
