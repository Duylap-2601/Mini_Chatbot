"""
setup_assistant.py — One-time script to create the OpenAI Assistant + Vector Store.

Run this ONCE before the first main.py run:
    python setup_assistant.py

It will print the ASSISTANT_ID and VECTOR_STORE_ID to add to your .env file.
"""

import os
import sys
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

SYSTEM_PROMPT = """You are OptiBot, the customer-support bot for OptiSigns.com.
• Tone: helpful, factual, concise.
• Only answer using the uploaded docs.
• Max 5 bullet points; else link to the doc.
• Cite up to 3 "Article URL:" lines per reply.

If the answer is not found in the documents, respond with: "I don't have information on that. Please visit https://support.optisigns.com or contact OptiSigns support."
"""

VECTOR_STORE_NAME = "OptiSigns Help Center"
ASSISTANT_NAME = "OptiBot"


def main():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key.startswith("sk-..."):
        print("ERROR: Set OPENAI_API_KEY in your .env file first.")
        sys.exit(1)

    client = OpenAI(api_key=api_key)

    # 1. Create Vector Store
    print(f"Creating vector store: '{VECTOR_STORE_NAME}'...")
    vs = client.vector_stores.create(name=VECTOR_STORE_NAME)
    print(f"  [OK] Vector Store ID: {vs.id}")

    # 2. Create Assistant linked to Vector Store
    print(f"\nCreating assistant: '{ASSISTANT_NAME}'...")
    assistant = client.beta.assistants.create(
        name=ASSISTANT_NAME,
        instructions=SYSTEM_PROMPT,
        model="gpt-4o-mini",          # cost-effective; swap to gpt-4o for higher quality
        tools=[{"type": "file_search"}],
        tool_resources={
            "file_search": {
                "vector_store_ids": [vs.id],
            }
        },
    )
    print(f"  [OK] Assistant ID: {assistant.id}")

    # 3. Print .env values to copy
    print("\n" + "=" * 50)
    print("Add these to your .env file:")
    print("=" * 50)
    print(f"OPENAI_ASSISTANT_ID={assistant.id}")
    print(f"OPENAI_VECTOR_STORE_ID={vs.id}")
    print("=" * 50)


if __name__ == "__main__":
    main()
