from chat import run_model_tool_loop
import streamlit as st

if __name__ == '__main__':
    while True:
        user_message = st.text_input("You:")
        if user_message:
            response = run_model_tool_loop(provider="groq",
                        model_name="groq/openai/gpt-oss-20b",
                        messages=[{"role": "user", "content": user_message}],  # <--- dùng tham số này
                        tools=[...],  # nếu dùng tool
                        debug=True)
            print("Response:", response)