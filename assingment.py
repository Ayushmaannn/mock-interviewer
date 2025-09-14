import streamlit as st
import google.generativeai as genai
import os
import time
from google.api_core.exceptions import ResourceExhausted
import PyPDF2
from io import BytesIO
import re

# Configure Gemini API
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# --- Helper functions (same as before, shortened here for clarity) ---
def get_gemini_response(prompt_text, chat_history=None, retries=3):
    model_name = "gemini-2.5-flash-lite"
    model = genai.GenerativeModel(model_name)
    for attempt in range(retries):
        try:
            if chat_history:
                chat = model.start_chat(history=chat_history)
                response = chat.send_message(prompt_text)
            else:
                response = model.generate_content(prompt_text)
            if response.text:
                return response.text
            else:
                st.error("Empty response from API.")
        except ResourceExhausted:
            wait_time = 60 * (attempt + 1)
            st.warning(f"⚠️ Rate limit hit. Retrying in {wait_time} seconds...")
            time.sleep(wait_time)
        except Exception as e:
            st.error(f"Unexpected error: {e}")
            return "Error occurred."
    return "⚠️ Interviewer unavailable. Please try later."

def analyze_resume(resume_text):
    prompt = f"""You are an AI Interviewer. Analyze the following resume text to identify any Excel-related skills or projects. Summarize them if found. If not, state that none were found.
    Resume text:
    {resume_text}
    """
    return get_gemini_response(prompt)

def get_interview_intro(resume_summary, user_name, interviewer_name):
    if resume_summary:
        prompt = f"""You are an AI Interviewer named {interviewer_name}. Candidate: {user_name}. Based on their resume summary: {resume_summary}, introduce yourself and explain the interview structure. Avoid brackets."""
    else:
        prompt = f"""You are an AI Interviewer named {interviewer_name}. Candidate: {user_name}. Introduce yourself and explain the interview structure. Avoid brackets."""
    return get_gemini_response(prompt)

def get_next_question(chat_history, user_name, interviewer_name):
    prompt = f"""You are an AI Interviewer. Candidate: {user_name}. Based on history, ask the next Excel-related question. Keep it clear and concise. Avoid fillers and brackets."""
    return get_gemini_response(prompt, chat_history)

def evaluate_answer(candidate_answer, chat_history, user_name, interviewer_name):
    prompt = f"""You are an AI Interviewer. Candidate: {user_name}. Evaluate their answer: "{candidate_answer}". Give a score (0-10) and short feedback. Avoid brackets."""
    return get_gemini_response(prompt, chat_history)

def generate_final_report(chat_history, user_name, interviewer_name):
    formatted_history = []
    for turn in chat_history:
        role = "Interviewer" if turn["role"] == "model" else user_name
        text = turn["parts"][0]["text"]
        formatted_history.append(f"{role}: {text}")
    history_str = "\n".join(formatted_history)
    prompt = f"""You are an AI Interviewer {interviewer_name}. Candidate: {user_name}.
Provide a structured performance summary with:
**Overall Impression**
**Strengths**
**Areas for Improvement**
**Specific Examples**

Conversation History:
{history_str}
"""
    return get_gemini_response(prompt)

def read_resume(uploaded_file):
    try:
        pdf_reader = PyPDF2.PdfReader(uploaded_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
        return text
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
        return None

# --- Session management ---
if "interview_state" not in st.session_state:
    st.session_state.interview_state = "initial"
if "history" not in st.session_state:
    st.session_state.history = []
if "report" not in st.session_state:
    st.session_state.report = None
if "question_count" not in st.session_state:
    st.session_state.question_count = 0
if "user_name" not in st.session_state:
    st.session_state.user_name = None
if "interviewer_name" not in st.session_state:
    st.session_state.interviewer_name = "Alex"
if "low_score_streak" not in st.session_state:
    st.session_state.low_score_streak = 0
if "all_reports" not in st.session_state:
    st.session_state.all_reports = {}  # store {username: report}

# --- Page Selection ---
st.sidebar.title("📋 Navigation")
page = st.sidebar.radio("Go to", ["Candidate Interview", "HR Login"])

# --- Candidate Interview Page ---
if page == "Candidate Interview":
    st.set_page_config(page_title="AI Excel Interviewer", page_icon="📊")
    st.title("📊 AI Excel Interviewer")

    st.sidebar.header("Interview Controls")
    user_name_input = st.sidebar.text_input("Enter your Name")
    resume_file = st.sidebar.file_uploader("Upload resume (PDF)", type="pdf")

    if st.sidebar.button("Start Interview"):
        if not user_name_input:
            st.sidebar.warning("Please enter your Name.")
        else:
            st.session_state.user_name = user_name_input
            st.session_state.interview_state = "in_progress"
            st.session_state.history = []
            st.session_state.report = None
            st.session_state.question_count = 0
            st.session_state.low_score_streak = 0

            resume_text = None
            if resume_file:
                with st.spinner("Analyzing resume..."):
                    resume_text = read_resume(resume_file)
                    if resume_text:
                        resume_summary = analyze_resume(resume_text)
                        intro_reply = get_interview_intro(resume_summary, st.session_state.user_name, st.session_state.interviewer_name)
                    else:
                        intro_reply = get_interview_intro(None, st.session_state.user_name, st.session_state.interviewer_name)
            else:
                intro_reply = get_interview_intro(None, st.session_state.user_name, st.session_state.interviewer_name)

            st.session_state.history.append({"role": "model", "parts": [{"text": intro_reply}]})
            with st.spinner("First question..."):
                first_q_prompt = f"""You are an AI Interviewer {st.session_state.interviewer_name}. Candidate: {st.session_state.user_name}. Ask the first Excel-related question. Avoid fillers and brackets."""
                first_q = get_gemini_response(first_q_prompt)
            st.session_state.history.append({"role": "model", "parts": [{"text": first_q}]})
            st.rerun()

    if st.sidebar.button("End Interview"):
        if st.session_state.history:
            with st.spinner("Generating report..."):
                final_report = generate_final_report(st.session_state.history, st.session_state.user_name, st.session_state.interviewer_name)
            st.session_state.report = final_report
            st.session_state.interview_state = "done"
            # Save to all_reports
            st.session_state.all_reports[st.session_state.user_name] = final_report
            st.rerun()
        else:
            st.sidebar.warning("No active session to end.")

    if st.session_state.interview_state == "in_progress":
        st.subheader("Interview Conversation")
        for message in st.session_state.history:
            role = "user" if message["role"] == "user" else "assistant"
            with st.chat_message(role):
                st.markdown(message["parts"][0]["text"])
        candidate_answer = st.chat_input("Your answer here...")
        if candidate_answer:
            st.session_state.history.append({"role": "user", "parts": [{"text": candidate_answer}]})
            with st.spinner("Evaluating..."):
                eval_reply = evaluate_answer(candidate_answer, st.session_state.history, st.session_state.user_name, st.session_state.interviewer_name)
            st.session_state.history.append({"role": "model", "parts": [{"text": eval_reply}]})
            score_match = re.search(r"Score:\s*(\d+)", eval_reply)
            score = int(score_match.group(1)) if score_match else 0
            if score <= 3:
                st.session_state.low_score_streak += 1
            else:
                st.session_state.low_score_streak = 0
            st.session_state.question_count += 1
            if st.session_state.low_score_streak >= 4 or st.session_state.question_count >= 15:
                st.info("Ending interview. Generating final report...")
                with st.spinner("Finalizing report..."):
                    final_report = generate_final_report(st.session_state.history, st.session_state.user_name, st.session_state.interviewer_name)
                st.session_state.report = final_report
                st.session_state.all_reports[st.session_state.user_name] = final_report
                st.session_state.interview_state = "done"
            else:
                with st.spinner("Next question..."):
                    next_q = get_next_question(st.session_state.history, st.session_state.user_name, st.session_state.interviewer_name)
                st.session_state.history.append({"role": "model", "parts": [{"text": next_q}]})
            st.rerun()

    elif st.session_state.interview_state == "done":
        st.subheader("📄 Final Interview Report")
        st.write(st.session_state.report)
    else:
        st.info("Please enter your name and click 'Start Interview'.")

# --- HR Login Page ---
elif page == "HR Login":
    st.header("🔑 HR Login")
    hr_username = st.text_input("HR Username")
    hr_password = st.text_input("HR Password", type="password")

    if st.button("Login"):
        if hr_username == "admin" and hr_password == "hr123":  # simple hardcoded login
            st.success("✅ Logged in as HR")
            st.subheader("📑 Candidate Reports")
            if st.session_state.all_reports:
                for user, report in st.session_state.all_reports.items():
                    with st.expander(f"Report for {user}"):
                        st.markdown(report)
            else:
                st.info("No reports available yet.")
        else:
            st.error("❌ Invalid HR credentials")
