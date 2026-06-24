import os
import anthropic

print("Starting Claude test...")

api_key = os.getenv("ANTHROPIC_API_KEY")

if not api_key:
    raise Exception("ANTHROPIC_API_KEY not found")

client = anthropic.Anthropic(
    api_key=api_key
)

response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=100,
    messages=[
        {
            "role": "user",
            "content": "Hello"
        }
    ]
)

print("SUCCESS:")
print(response.content[0].text)
