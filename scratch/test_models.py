import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=api_key)

try:
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents='Hello, list the top 3 features of OptiSigns digital signage.',
    )
    print("Response:")
    print(response.text)
except Exception as e:
    print("Error calling gemini-2.5-flash:", e)
