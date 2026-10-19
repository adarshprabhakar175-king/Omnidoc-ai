import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")
print("API Key loaded:", "Yes" if api_key else "No")

try:
    # Model name yahan gemini-2.0-flash kar diya hai
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=api_key)
    response = llm.invoke("Hello! Say 'Gemini is working' if you can read this.")
    
    print("\nSUCCESS! Model Response:")
    print(response.content)
except Exception as e:
    print("\nERROR OCCURRED:")
    print(str(e))