import streamlit as st
from google import genai
import os
import re
import requests
import json
import pandas as pd
from datetime import datetime
from PIL import Image
import streamlit.components.v1 as components
from dotenv import load_dotenv

# 1. 화면 설정 및 환경변수
st.set_page_config(layout="wide", page_title="건강 스케줄러")

st.markdown("""
    <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        .block-container {padding-top: 2rem; padding-bottom: 2rem;}
        .stButton>button {
            border-radius: 8px; font-weight: 600;
            border: 1px solid #E2E8F0; transition: all 0.3s ease;
        }
        .stButton>button:hover {
            transform: translateY(-2px); box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }
    </style>
""", unsafe_allow_html=True)

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
news_api_key = os.getenv("NEWS_API_KEY")

if not api_key:
    st.error("🚨 API 키를 찾을 수 없습니다. .env 파일을 확인하세요.")
    st.stop()

client = genai.Client(api_key=api_key)

DB_FILE = "user_db.json"

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: return {}
    return {}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def calculate_metrics(weight, height, age, gender):
    try:
        w, h, a = float(weight), float(height), int(age)
        bmi = w / ((h / 100) ** 2)
        bmr = (10 * w) + (6.25 * h) - (5 * a) + (5 if gender == "남성" else -161)
        return round(bmi, 1), round(bmr, 0)
    except: return None, None

# Session State 초기화
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "schedule_data" not in st.session_state: st.session_state.schedule_data = None
if "current_goal" not in st.session_state: st.session_state.current_goal = None
if "user_info" not in st.session_state: st.session_state.user_info = {}

# -----------------------------------------
# ✅ [개선 1] 사이드바 영역: 로그인 및 사용자 설정
# -----------------------------------------
with st.sidebar:
    st.title("⚙️ SPOTTER 설정")
    if not st.session_state.logged_in:
        username = st.text_input("사용자 이름을 입력하세요")
        if st.button("로그인"):
            if not username.strip():
                st.error("이름을 정확히 입력해주세요.")
            else:
                st.session_state.username = username.strip()
                st.session_state.logged_in = True
                st.session_state.user_info = load_db().get(st.session_state.username, {})
                st.rerun()
    else:
        st.success(f"**{st.session_state.username}**님, 환영합니다!")
        saved = st.session_state.user_info
        
        st.markdown("### 📋 내 신체 및 일정 정보")
        gender_options = ["남성", "여성"]
        saved_gender = saved.get("gender", "남성")
        gender = st.selectbox("성별", gender_options, index=gender_options.index(saved_gender) if saved_gender in gender_options else 0)
        age = st.text_input("나이 (만)", value=saved.get("age", ""))
        weight = st.text_input("몸무게 (kg)", value=saved.get("weight", ""))
        height = st.text_input("키 (cm)", value=saved.get("height", ""))
        muscle = st.text_input("근육량 (kg)", value=saved.get("muscle", ""))
        work_start = st.text_input("업무 시작 (예: 09:00)", value=saved.get("work_start", "09:00"))
        work_end = st.text_input("업무 종료 (예: 18:00)", value=saved.get("work_end", "18:00"))
        commute = st.text_input("편도 이동시간 (예: 30분)", value=saved.get("commute", "30분"))
        sleep = st.text_input("목표 수면시간 (시간)", value=saved.get("sleep", "8"))
        injury = st.text_input("부상 상태", value=saved.get("injury", "없음"))
        
        if st.button("설정 저장"):
            db = load_db()
            user_data = db.get(st.session_state.username, {})
            user_data.update({"gender": gender, "age": age, "weight": weight, "height": height, "muscle": muscle, "work_start": work_start, "work_end": work_end, "commute": commute, "sleep": sleep, "injury": injury})
            
            today_str = datetime.now().strftime("%Y-%m-%d")
            if "history" not in user_data: user_data["history"] = {}
            try: w_float = float(weight) if weight else None
            except: w_float = None
            try: m_float = float(muscle) if muscle else None
            except: m_float = None
            
            user_data["history"][today_str] = {"weight": w_float, "muscle": m_float}
            db[st.session_state.username] = user_data
            save_db(db)
            st.session_state.user_info = user_data
            st.toast("✅ 설정이 저장되었습니다.")
            
        st.markdown("---")
        if st.button("로그아웃"):
            st.session_state.clear()
            st.rerun()

# -----------------------------------------
# ✅ [개선 2] 메인 영역: 탭 기반 UI 구조 분리
# -----------------------------------------
st.title("📅 SPOTTER 대시보드")

if st.session_state.logged_in:
    tab_dash, tab_sched, tab_vision = st.tabs(["📊 통계 대시보드", "📅 맞춤 스케줄 설계", "📸 AI 식단 감별사"])
    
    # --- 탭 1: 통계 대시보드 ---
    with tab_dash:
        history = st.session_state.user_info.get("history", {})
        if history:
            df = pd.DataFrame.from_dict(history, orient='index')
            df.index = pd.to_datetime(df.index)
            df = df.sort_index().dropna(how='all')
            
            if not df.empty:
                st.subheader("📈 나의 신체 변화 통계")
                t1, t2, t3 = st.tabs(["🗓️ 일별 기록", "📊 주차별 평균", "📉 월별 랭킹"])
                with t1: st.line_chart(df[['weight', 'muscle']])
                with t2:
                    weekly_df = df.resample('W-SUN').mean()
                    if len(weekly_df) >= 1: st.line_chart(weekly_df[['weight', 'muscle']])
                    else: st.info("주차별 통계 데이터가 부족합니다.")
                with t3:
                    monthly_df = df.resample('ME').mean()
                    if len(monthly_df) >= 1: st.line_chart(monthly_df[['weight', 'muscle']])
                    else: st.info("월간 통계 데이터가 부족합니다.")
            else: st.info("기록된 신체 데이터가 없습니다.")
        else:
            st.info("좌측 사이드바에서 신체 정보를 입력하고 저장해주세요.")

# --- 탭 2: 맞춤 스케줄 설계 ---
    with tab_sched:
        st.subheader("🎯 오늘의 목표 설정")
        goal = st.selectbox("오늘의 건강 목표", ["다이어트", "건강 유지", "근육량 증가", "수면 개선 & 스트레스 관리"])
        target_muscles = []
        if goal == "근육량 증가":
            target_muscles = st.multiselect("자극할 운동 부위", ["등", "가슴", "팔", "어깨", "하체"])
            
        if st.button("🚀 스케줄 생성하기", use_container_width=True):
            st.session_state.current_goal = goal
            def get_val(val): return val if val and val != "모름" else "정보 없음"
            
            extra_info = ""
            prompt_instruction = ""
            
            if goal == "다이어트":
                bmi, bmr = calculate_metrics(weight, height, age, gender)
                if bmi and bmr:
                    tdee = bmr * 1.2 
                    extra_info = f"[팩트 폭력] BMI {bmi}. TDEE 약 {tdee}kcal."
                prompt_instruction = "탄30, 단35, 지35 비율 식단. 유산소 위주 지침."
            elif goal == "근육량 증가":
                m_str = ", ".join(target_muscles) if target_muscles else "전신"
                prompt_instruction = f"탄50, 단30, 지20 벌크업 식단. {m_str} 중심 웨이트 루틴."
            elif goal == "건강 유지":
                prompt_instruction = "탄40, 단30, 지30 식단. 가벼운 생활 운동."
            elif goal == "수면 개선 & 스트레스 관리":
                prompt_instruction = "연구 피로도 낮추고 수면 질 높이는 지침. 식단 제외."

            prompt = f"""사용자: 체중{get_val(weight)}kg. 부상: {get_val(injury)}
[제약 조건] 업무시간({get_val(work_start)}~{get_val(work_end)})은 집중, 전후 {get_val(commute)} 이동시간 보장.
{extra_info} / 특별 지시: {prompt_instruction}

[출력 템플릿]
[SUMMARY] 요약 2줄 [/SUMMARY]
[CALENDAR] 시간대별 마크다운 표 [/CALENDAR]
[CHECKLIST] 5가지 목표 (엔터구분) [/CHECKLIST]
[EXERCISE] 이모지 활용 행동지침 [/EXERCISE]
[DIET] 식단추천 [/DIET]
[AVOID] 피할음식 [/AVOID]"""

            with st.spinner('스케줄 설계 중...'):
                try:
                    res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                    def extract(tag, text):
                        match = re.search(fr'\[{tag}\](.*?)\[\/{tag}\]', text, re.DOTALL | re.IGNORECASE)
                        return match.group(1).strip() if match else None
                    
                    summary = extract("SUMMARY", res.text)
                    calendar = extract("CALENDAR", res.text)
                    
                    # ✅ [개선] 파싱 실패 시 원본 데이터를 화면에 강제로 띄우는 방어 로직
                    if not summary or not calendar:
                        st.error("🚨 AI가 지정된 출력 양식을 무시했습니다. 아래 원본 응답을 확인하세요.")
                        st.info(res.text) # AI가 실제로 뱉은 텍스트를 그대로 출력
                        st.session_state.schedule_data = None
                    else:
                        st.session_state.schedule_data = {
                            "summary": summary, 
                            "calendar": calendar,
                            "checklist": [t.strip() for t in (extract("CHECKLIST", res.text) or "").split('\n') if t.strip()],
                            "exercise": extract("EXERCISE", res.text), 
                            "diet": extract("DIET", res.text), 
                            "avoid": extract("AVOID", res.text)
                        }
                except Exception as e:
                    st.error(f"서버 오류가 발생했습니다: {e}")
        
        # 스케줄 결과 출력
        if st.session_state.schedule_data:
            data = st.session_state.schedule_data
            goal_now = st.session_state.current_goal
            
            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("#### 📅 오늘 일과 캘린더")
                st.markdown(data["calendar"] or "오류 발생")
                if data.get("exercise"):
                    st.info(data["exercise"])
            with col2:
                st.markdown("#### 📝 스케줄 요약")
                st.success(data["summary"] or "오류 발생")
                
                tasks = data["checklist"]
                if tasks:
                    completed = sum(1 for i, t in enumerate(tasks) if st.checkbox(t, key=f"check_{i}"))
                    st.progress(completed / len(tasks) if len(tasks)>0 else 0, text=f"달성도: {int(completed/len(tasks)*100)}%")
                    
                if goal_now != "수면 개선 & 스트레스 관리" and data.get("diet"):
                    st.warning(data["diet"])
                    st.error(data["avoid"])
        # 스케줄 결과 출력
        if st.session_state.schedule_data:
            data = st.session_state.schedule_data
            goal_now = st.session_state.current_goal
            
            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("#### 📅 오늘 일과 캘린더")
                st.markdown(data["calendar"] or "오류 발생")
                if data.get("exercise"):
                    st.info(data["exercise"])
            with col2:
                st.markdown("#### 📝 스케줄 요약")
                st.success(data["summary"] or "오류 발생")
                
                tasks = data["checklist"]
                if tasks:
                    completed = sum(1 for i, t in enumerate(tasks) if st.checkbox(t, key=f"check_{i}"))
                    st.progress(completed / len(tasks) if len(tasks)>0 else 0, text=f"달성도: {int(completed/len(tasks)*100)}%")
                    
                if goal_now != "수면 개선 & 스트레스 관리" and data.get("diet"):
                    st.warning(data["diet"])
                    st.error(data["avoid"])

    # --- 탭 3: AI 식단 감별사 ---
    with tab_vision:
        st.subheader("📸 AI 식단 감별사")
        goal_now = st.session_state.current_goal
        if not goal_now or goal_now == "수면 개선 & 스트레스 관리":
            st.warning("먼저 '맞춤 스케줄 설계' 탭에서 식단 관련 목표(다이어트, 근육량 증가 등)로 스케줄을 생성해주세요.")
        else:
            uploaded_file = st.file_uploader("음식 사진 업로드", type=["jpg", "jpeg", "png"])
            if uploaded_file is not None:
                image = Image.open(uploaded_file)
                st.image(image, caption='업로드된 식단', use_container_width=True)
                if st.button("식단 팩트체크 받기", use_container_width=True):
                    with st.spinner("AI 분석 중..."):
                        try:
                            vision_prompt = f"이 사진의 음식을 분석해서 칼로리와 매크로를 추정하고, 현재 목표({goal_now})에 맞춰 직설적인 조언 3줄."
                            vision_res = client.models.generate_content(model='gemini-2.5-flash', contents=[vision_prompt, image])
                            st.error(vision_res.text)
                        except Exception as e:
                            st.error("이미지 분석 실패.")
else:
    st.info("좌측 사이드바 메뉴를 열어 로그인을 진행해주세요. (모바일의 경우 좌측 상단 '>' 화살표 터치)")