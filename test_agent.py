from groq import Groq

import os

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

chat_completion = client.chat.completions.create(
    messages=[
        {
            "role": "user",
            "content": "What wil the the use of an app that can predict prices of products due to information from an  LLM agent and compare across different platforms and saves in dctc bcse cnd the cgent is u grog who will benefit from this and does this help nigeria in any waay and to wht extent",
        }
    ],
    model="llama-3.3-70b-versatile",
)

print(chat_completion.choices[0].message.content) 