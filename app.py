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
        /* 우측 상단 기본 메뉴 햄버거 아이콘 숨기기 */
        #MainMenu {visibility: hidden;}
        /* 하단 'Made with Streamlit' 워터마크 숨기기 */
        footer {visibility: hidden;}
        /* 상단 여백(Padding) 줄이기 */
        .block-container {padding-top: 2rem; padding-bottom: 2rem;}
        
        /* 버튼 디자인 세련되게 깎기 */
        .stButton>button {
            border-radius: 8px; /* 모서리를 둥글게 */
            font-weight: 600;   /* 글씨를 두껍게 */
            border: 1px solid #E2E8F0; /* 테두리 연하게 */
            transition: all 0.3s ease; /* 마우스 오버 시 부드러운 애니메이션 */
        }
        .stButton>button:hover {
            transform: translateY(-2px); /* 마우스를 올리면 살짝 위로 떠오르는 효과 */
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); /* 그림자 효과 */
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
selected_model = 'gemini-2.5-flash'

# 💾 로컬 파일 데이터베이스 헬퍼 함수
DB_FILE = "user_db.json"

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# 2. BMR 및 BMI 계산 함수
def calculate_metrics(weight, height, age, gender):
    try:
        w = float(weight)
        h = float(height)
        a = int(age)
        
        bmi = w / ((h / 100) ** 2)
        
        if gender == "남성":
            bmr = (10 * w) + (6.25 * h) - (5 * a) + 5
        else:
            bmr = (10 * w) + (6.25 * h) - (5 * a) - 161
            
        return round(bmi, 1), round(bmr, 0)
    except:
        return None, None

# 3. 화면 UI 구성
st.title("📅 SPOTTER")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "schedule_data" not in st.session_state:
    st.session_state.schedule_data = None
if "current_goal" not in st.session_state:
    st.session_state.current_goal = None
if "user_info" not in st.session_state:
    st.session_state.user_info = {}

if not st.session_state.logged_in:
    username = st.text_input("사용자 이름을 입력하세요")
    if st.button("로그인"):
        if not username.strip():
            st.error("사용자 이름을 정확히 입력해주세요.")
        else:
            st.session_state.username = username.strip()
            st.session_state.logged_in = True
            
            db = load_db()
            st.session_state.user_info = db.get(st.session_state.username, {})
            st.rerun()
else:
    st.write(f"환영합니다, **{st.session_state.username}**님!")
    
    # ✅ [기능 1] 신체 변화 추적 대시보드 렌더링
    saved = st.session_state.user_info
    history = saved.get("history", {})
    
    if history:
        st.markdown("---")
        st.subheader("📈 나의 신체 변화 추이")
        # JSON 딕셔너리를 Pandas 데이터프레임으로 변환
        df = pd.DataFrame.from_dict(history, orient='index')
        df.index = pd.to_datetime(df.index)
        df = df.sort_index() # 날짜순 정렬
        
        # 값이 있는 데이터만 차트로 표시
        chart_df = df.dropna(how='all')
        if not chart_df.empty:
            st.line_chart(chart_df[['weight', 'muscle']])
        else:
            st.info("아직 표시할 신체 변화 데이터가 충분하지 않습니다.")
    
    st.markdown("---")
    
    goal = st.selectbox(
        "오늘의 건강 목표 (필수)", 
        ["다이어트", "건강 유지", "근육량 증가", "수면 개선 & 스트레스 관리"]
    )
    
    with st.form("health_info_form"):
        target_muscles = []
        if goal == "근육량 증가":
            target_muscles = st.multiselect(
                "오늘 자극할 운동 부위를 선택하세요", 
                ["등", "가슴", "팔", "어깨", "하체"]
            )
            
        with st.expander("상세 정보 입력 (스케줄 정밀도 향상을 위한 필수 데이터)"):
            col_a, col_b = st.columns(2)
            with col_a:
                gender_options = ["남성", "여성"]
                saved_gender = saved.get("gender", "남성")
                gender_idx = gender_options.index(saved_gender) if saved_gender in gender_options else 0
                gender = st.selectbox("성별", gender_options, index=gender_idx)
                
                age = st.text_input("나이 (만)", value=saved.get("age", ""))
                weight = st.text_input("몸무게 (kg)", value=saved.get("weight", ""))
                height = st.text_input("키 (cm)", value=saved.get("height", ""))
                muscle = st.text_input("근육량 (kg)", value=saved.get("muscle", ""))
                
            with col_b:
                work_start = st.text_input("업무 시작 시간 (예: 09:00)", value=saved.get("work_start", "09:00"))
                work_end = st.text_input("업무 종료 시간 (예: 18:00)", value=saved.get("work_end", "18:00"))
                commute = st.text_input("편도 이동 시간 (예: 30분)", value=saved.get("commute", "30분"))
                
                sleep = st.text_input("목표 수면시간 (시간)", value=saved.get("sleep", "8"))
                injury = st.text_input("부상 상태", value=saved.get("injury", "없음"))

        submitted = st.form_submit_button("오늘의 스케줄 생성하기")

    # 4. 메인 로직 및 데이터 저장
    if submitted:
        st.session_state.current_goal = goal
        def get_val(val): return val if val and val != "모름" else "정보 없음"
        
        # ✅ [기능 1] 날짜별 기록 누적 저장 로직
        db = load_db()
        user_data = db.get(st.session_state.username, {})
        
        user_data.update({
            "gender": gender,
            "age": age,
            "weight": weight,
            "height": height,
            "muscle": muscle,
            "work_start": work_start,
            "work_end": work_end,
            "commute": commute,
            "sleep": sleep,
            "injury": injury
        })
        
        if "history" not in user_data:
            user_data["history"] = {}
            
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        try:
            w_float = float(weight) if weight else None
        except:
            w_float = None
            
        try:
            m_float = float(muscle) if muscle else None
        except:
            m_float = None

        user_data["history"][today_str] = {
            "weight": w_float,
            "muscle": m_float
        }
        
        db[st.session_state.username] = user_data
        save_db(db)
        st.session_state.user_info = user_data
        
        extra_info = ""
        prompt_instruction = ""
        
        if goal == "다이어트":
            bmi, bmr = calculate_metrics(weight, height, age, gender)
            if bmi and bmr:
                avg_bmi = 22.0
                bmi_diff = round(bmi - avg_bmi, 1)
                tdee = bmr * 1.2 
                ramen_count = round((tdee - 500) / 500, 1)
                
                extra_info = f"""
                [팩트 폭력 결과]
                현재 BMI는 {bmi}입니다. 정상 평균 BMI(22.0) 대비 {bmi_diff}만큼 떨어져 있는 심각한 상태입니다.
                하루 권장 칼로리 소모량(TDEE)은 약 {tdee}kcal입니다.
                다이어트를 위해 하루 500kcal를 덜 먹는다고 가정할 때, 남은 칼로리를 라면(500kcal)으로 환산하면 하루에 라면 {ramen_count}개 정도만 먹을 수 있는 수준입니다.
                """
            prompt_instruction = "탄수화물 30%, 단백질 35%, 지방 35% 비율에 맞춘 식단 추천. 유산소 위주의 운동 지침. 피해야 할 음식 강력 경고."

        elif goal == "근육량 증가":
            muscle_str = ", ".join(target_muscles) if target_muscles else "전신"
            prompt_instruction = f"탄수화물 50%, 단백질 30%, 지방 20% 비율에 맞춘 벌크업 식단. 선택 부위({muscle_str}) 중심 1시간 웨이트 루틴. 근손실 유발 음식 경고."

        elif goal == "건강 유지":
            prompt_instruction = "탄수화물 40%, 단백질 30%, 지방 30% 밸런스 식단. 가벼운 스트레칭과 생활 운동. 염분/당분 높은 피해야 할 음식 경고."

        elif goal == "수면 개선 & 스트레스 관리":
            prompt_instruction = "업무 및 연구로 인한 뇌 피로도를 낮추고 수면의 질을 높이는 행동 지침 작성. [DIET]와 [AVOID] 태그 및 식단 관련 내용은 절대 출력하지 마세요."

        prompt = f"""
        사용자 상태: 체중{get_val(weight)}kg, 키{get_val(height)}cm. 부상: {get_val(injury)}
        
        [일정 제약 조건]
        - 캘린더 작성 시, 업무 시작 시간({get_val(work_start)})부터 종료 시간({get_val(work_end)})까지는 무조건 '업무/연구 집중'으로만 채우세요. 
        - 또한 업무 시작 전과 종료 후 각각 {get_val(commute)} 동안은 '출근/퇴근 이동' 시간으로 반드시 비워두세요.
        - 이 제약 시간대에는 절대 개인 운동이나 다른 건강 관리 일정을 배치해서는 안 됩니다.
        
        {extra_info}
        특별 지시: {prompt_instruction}
        
        [엄격한 출력 지시사항]
        AI 모델은 인사말, 서론, 결론을 절대 출력하지 마세요.
        아래 [출력 템플릿]의 괄호 태그 구조를 그대로 복사하여 내용만 채워넣으세요.
        
        [출력 템플릿]
        [SUMMARY]
        여기에 스케줄 핵심 요약 2줄 작성
        [/SUMMARY]
        
        [CALENDAR]
        여기에 하루 시간대별 일과 스케줄을 마크다운 표(Table)로 작성 (위의 일정 제약 조건을 완벽히 지킬 것)
        [/CALENDAR]
        
        [CHECKLIST]
        여기에 오늘 실천할 5가지 핵심 목표를 하이픈(-) 없이 엔터로만 구분하여 작성
        [/CHECKLIST]
        
        [EXERCISE]
        여기에 눈에 띄는 이모지를 사용하여 오늘 해야 할 행동 지침 작성
        [/EXERCISE]
        """
        
        if goal != "수면 개선 & 스트레스 관리":
            prompt += """
        [DIET]
        여기에 아침, 점심, 저녁 메뉴를 매크로 비율에 맞춰 추천
        [/DIET]
        
        [AVOID]
        여기에 절대 먹지 말아야 할 음식 경고 작성
        [/AVOID]
            """

        with st.spinner('AI가 이동 및 근무 시간을 고려하여 맞춤형 스케줄을 설계 중입니다...'):
            models_to_try = ['gemini-2.5-flash', 'gemini-1.5-flash']
            
            for attempt, model_name in enumerate(models_to_try):
                try:
                    if attempt > 0:
                        st.warning(f"메인 서버 혼잡으로 인해 대체 AI 모델({model_name})로 전환하여 재시도합니다...")
                        
                    res = client.models.generate_content(model=model_name, contents=prompt)
                    raw_text = res.text
                    
                    def extract(tag, text):
                        match = re.search(fr'\[{tag}\](.*?)\[\/{tag}\]', text, re.DOTALL | re.IGNORECASE)
                        return match.group(1).strip() if match else None

                    summary = extract("SUMMARY", raw_text)
                    calendar = extract("CALENDAR", raw_text)
                    
                    if not summary and not calendar:
                        st.error("🚨 AI가 지정된 양식을 따르지 않았습니다. 아래 원본을 확인하세요.")
                        st.info(raw_text)
                        st.session_state.schedule_data = None
                        break

                    st.session_state.schedule_data = {
                        "summary": summary or "요약을 불러오지 못했습니다.",
                        "calendar": calendar or "캘린더를 불러오지 못했습니다.",
                        "checklist": [t.strip() for t in (extract("CHECKLIST", raw_text) or "체크리스트 없음").split('\n') if t.strip()],
                        "exercise": extract("EXERCISE", raw_text),
                        "diet": extract("DIET", raw_text),
                        "avoid": extract("AVOID", raw_text),
                        "extra_info": extra_info,
                    }
                    
                    st.session_state.used_model = model_name
                    break  
                    
                except Exception as e:
                    st.toast(f"🚨 {model_name} 응답 실패.")
                    if model_name == models_to_try[-1]:
                        st.error("🚨 서버 오류가 지속됩니다. 잠시 후 다시 시도해주세요.")
                        st.session_state.schedule_data = None

    # 5. 결과 렌더링
    if st.session_state.schedule_data:
        data = st.session_state.schedule_data
        goal_now = st.session_state.current_goal
        used_model = st.session_state.get("used_model", "알 수 없음")
        
        st.success(f"'{goal_now}' 목표 스케줄이 생성되었습니다! (사용된 AI: {used_model})")
        
        if data.get("extra_info"):
            st.error(data["extra_info"])
            
        if goal_now == "건강 유지":
            st.subheader("📰 오늘의 건강 헤드라인")
            if not news_api_key:
                st.warning("News API 키가 설정되지 않았습니다. .env 파일을 확인하세요.")
            else:
                try:
                    news_res = requests.get(f"https://newsapi.org/v2/top-headlines?category=health&apiKey={news_api_key}&pageSize=3")
                    if news_res.status_code == 200:
                        articles = news_res.json().get("articles", [])
                        for idx, art in enumerate(articles):
                            st.markdown(f"**{idx+1}. [{art['title']}]({art['url']})**")
                except Exception as e:
                    st.error("뉴스 로딩 실패")
                    
        if goal_now == "수면 개선 & 스트레스 관리":
            st.subheader("🎧 수면 유도 백색소음 & ON/OFF 타이머")
            st.markdown("[👉 추천 백색소음 유튜브 링크 재생하기 (클릭)](https://www.youtube.com/watch?v=nMfPqeZjc2c)")
            
            sleep_hours = float(saved.get("sleep", "8")) if saved.get("sleep", "8").replace('.','',1).isdigit() else 8.0
            sleep_secs = int(sleep_hours * 3600)
            
            html_code = f"""
            <div style="background-color:#f0f2f6; padding:20px; border-radius:10px; text-align:center; font-family:sans-serif;">
                <h2 id="time_display" style="font-size:3rem; margin-bottom:10px; color:#333;">00:00:00</h2>
                <button id="toggle_btn" onclick="toggleTimer()" style="padding:10px 30px; font-size:18px; cursor:pointer; background-color:#4CAF50; color:white; border:none; border-radius:5px; font-weight:bold;">▶ 시작</button>
                <button onclick="resetTimer()" style="padding:10px 20px; font-size:18px; cursor:pointer; background-color:#f44336; color:white; border:none; border-radius:5px; font-weight:bold; margin-left:10px;">↺ 초기화</button>
            </div>
            <script>
            let timerInterval;
            let isRunning = false;
            let initialTime = {sleep_secs};
            let remainingTime = initialTime;

            function updateDisplay() {{
                let h = Math.floor(remainingTime / 3600);
                let m = Math.floor((remainingTime % 3600) / 60);
                let s = Math.floor(remainingTime % 60);
                document.getElementById("time_display").innerText = 
                    String(h).padStart(2, '0') + ":" + 
                    String(m).padStart(2, '0') + ":" + 
                    String(s).padStart(2, '0');
            }}

            function toggleTimer() {{
                let btn = document.getElementById("toggle_btn");
                if (isRunning) {{
                    clearInterval(timerInterval);
                    btn.innerText = "▶ 계속";
                    btn.style.backgroundColor = "#4CAF50";
                    isRunning = false;
                }} else {{
                    if(remainingTime <= 0) remainingTime = initialTime;
                    timerInterval = setInterval(function() {{
                        remainingTime--;
                        updateDisplay();
                        if (remainingTime <= 0) {{
                            clearInterval(timerInterval);
                            alert("목표 수면 시간이 지났습니다! 기상하세요!");
                            btn.innerText = "▶ 시작";
                            btn.style.backgroundColor = "#4CAF50";
                            isRunning = false;
                        }}
                    }}, 1000);
                    btn.innerText = "⏸ 일시정지";
                    btn.style.backgroundColor = "#ff9800";
                    isRunning = true;
                }}
            }}
            
            function resetTimer() {{
                clearInterval(timerInterval);
                remainingTime = initialTime;
                updateDisplay();
                let btn = document.getElementById("toggle_btn");
                btn.innerText = "▶ 시작";
                btn.style.backgroundColor = "#4CAF50";
                isRunning = false;
            }}

            updateDisplay();
            </script>
            """
            components.html(html_code, height=200)

        st.markdown("---")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📅 오늘 일과 캘린더")
            st.markdown(data["calendar"])
            
            if data.get("exercise"):
                st.markdown("---")
                st.subheader("🔥 오늘의 행동 지침")
                st.info(data["exercise"])
            
        with col2:
            st.subheader("📝 스케줄 요약")
            st.info(data["summary"])
            
            st.markdown("---")
            st.subheader("✅ 오늘의 체크리스트")
            tasks = data["checklist"]
            if tasks:
                completed = 0
                for i, task in enumerate(tasks):
                    if st.checkbox(task, key=f"check_{i}"): completed += 1
                prog = completed / len(tasks)
                st.progress(prog, text=f"**달성도: {int(prog*100)}%**")
                
            if goal_now != "수면 개선 & 스트레스 관리" and data.get("diet") and data.get("avoid"):
                st.markdown("---")
                st.subheader("🍽️ 매크로 맞춤 식단 추천")
                st.success(data["diet"])
                st.subheader("🚫 절대 피해야 할 음식")
                st.error(data["avoid"])
                
        # ✅ [기능 2] 사진 찍어 올리는 AI 식단 감별사 (수면 관리 제외)
        if goal_now != "수면 개선 & 스트레스 관리":
            st.markdown("---")
            st.subheader("📸 AI 식단 감별사 (현재 목표 맞춤 평가)")
            uploaded_file = st.file_uploader("오늘 먹을 식단 사진을 올려주세요. AI가 매크로를 분석합니다.", type=["jpg", "jpeg", "png"])
            
            if uploaded_file is not None:
                image = Image.open(uploaded_file)
                st.image(image, caption='업로드된 식단', use_container_width=True)
                
                if st.button("식단 팩트체크 받기"):
                    with st.spinner("AI가 음식의 성분을 분석 중입니다..."):
                        try:
                            vision_prompt = f"이 사진의 음식을 분석해서 대략적인 칼로리와 매크로(탄/단/지)를 추정해줘. 그리고 사용자의 현재 목표({goal_now})에 비추어봤을 때 이 식단이 적절한지 아주 직설적이고 뼈 때리는 조언을 3줄 이내로 해줘."
                            vision_res = client.models.generate_content(
                                model='gemini-2.5-flash',
                                contents=[vision_prompt, image]
                            )
                            st.warning(vision_res.text)
                        except Exception as e:
                            st.error(f"이미지 분석 중 오류가 발생했습니다: {e}")
            
    st.markdown("---")
    if st.button("로그아웃"):
        st.session_state.clear()
        st.rerun()