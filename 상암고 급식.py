import run
# -*- coding: utf-8 -*-
"""상암고 급식정보 Streamlit 앱 (SSL 검증 기본 OFF)"""

import streamlit as st
import requests
import datetime
import pytz
import re

# ================= 기본 UI 설정 =================
st.set_page_config(page_title="상암고 급식정보", page_icon="🍱", layout="centered")
st.title("🍱 상암고 급식정보")
st.caption("데이터 출처: NEIS Open API / 상암고(교육청코드 B10, 학교코드 7010806)")

# ================= 사이드바 옵션 =================
with st.sidebar:
    st.subheader("옵션")
    api_key = st.text_input(
        "NEIS API KEY (선택)",
        value="",
        type="password",
        help="없어도 조회는 가능하나, 쿼터/안정성 측면에서 키 사용을 권장합니다."
    )
    # SSL 인증서 검증 기본 OFF
    verify_ssl = st.toggle(
        "SSL 인증서 검사",
        value=False,
        help="일부 네트워크/환경에서 SSL 오류가 발생할 수 있습니다. 오류 시 OFF로 사용하세요."
    )
    st.markdown("---")
    st.markdown("**표시 옵션**")
    remove_allergen_nums = st.toggle("알레르기 숫자 제거", value=True)
    remove_paren_and_dots = st.toggle("괄호/마침표 제거", value=True)

# ================= 날짜 설정 =================
kst = pytz.timezone("Asia/Seoul")
today_kst = datetime.datetime.now(kst).date()
sel_date = st.date_input("날짜 선택", value=today_kst, format="YYYY-MM-DD")
yyyymmdd = sel_date.strftime("%Y%m%d")

# ================= 유틸 함수 =================
def build_neis_url(date_str: str) -> str:
    """
    NEIS 급식 API URL 생성
    """
    base = "https://open.neis.go.kr/hub/mealServiceDietInfo"
    params = {
        "ATPT_OFCDC_SC_CODE": "B10",   # 서울특별시교육청
        "SD_SCHUL_CODE": "7010806",    # 상암고등학교
        "Type": "json",
        "MLSV_YMD": date_str
    }
    if api_key.strip():
        params["KEY"] = api_key.strip()

    qs = "&".join([f"{k}={v}" for k, v in params.items()])
    return f"{base}?{qs}"

def clean_menu_text(text: str,
                    drop_nums: bool = True,
                    drop_paren_and_dots: bool = True) -> str:
    """
    주어진 원본 코드 로직을 반영한 메뉴 텍스트 정리 함수
    - <br/> → 줄바꿈
    - 숫자(알레르기 표기) 제거
    - 괄호/마침표 제거
    """
    if not text:
        return ""
    # <br/> → 줄바꿈
    text = text.replace("<br/>", "\n")

    # 알레르기 숫자 제거
    if drop_nums:
        text = re.sub(r"\d", "", text)

    # 괄호/마침표 제거
    if drop_paren_and_dots:
        text = text.replace("(", "").replace(")", "").replace(".", "")

    # 다중 공백 정리 및 라인 트리밍
    text = re.sub(r"[ \t]+", " ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    return text.strip()

@st.cache_data(ttl=600, show_spinner=False)
def fetch_meal(date_str: str, verify_cert: bool = False):
    """
    NEIS에서 급식 JSON을 받아 파싱 결과를 반환.
    반환:
      - 성공: {"rows": [...], "raw": <응답텍스트>}
      - 실패: {"error": "...", "status": <int|None>, "raw": <텍스트|"">}
    """
    url = build_neis_url(date_str)
    try:
        resp = requests.get(url, timeout=10, verify=verify_cert)
    except requests.exceptions.SSLError as e:
        return {"error": f"SSL 오류: {e}", "status": None, "raw": ""}
    except requests.exceptions.RequestException as e:
        return {"error": f"요청 오류: {e}", "status": None, "raw": ""}

    if resp.status_code != 200:
        return {"error": "HTTP 오류", "status": resp.status_code, "raw": resp.text}

    # JSON 파싱
    try:
        data = resp.json()
    except ValueError:
        return {"error": "JSON 파싱 실패", "status": resp.status_code, "raw": resp.text}

    # 정상 구조인지 확인
    if "mealServiceDietInfo" not in data:
        # 결과 없음 등의 경우 RESULT 메시지가 올 수 있음
        result_msg = ""
        try:
            result_msg = data.get("RESULT", {}).get("MESSAGE", "")
        except Exception:
            pass
        return {
            "error": f"데이터 없음 또는 비정상 응답. {result_msg}".strip(),
            "status": resp.status_code,
            "raw": resp.text
        }

    # 실제 급식 행 추출
    try:
        rows = data["mealServiceDietInfo"][1]["row"]
    except Exception:
        return {
            "error": "예상한 위치에 급식 데이터가 없습니다.",
            "status": resp.status_code,
            "raw": resp.text
        }

    return {"rows": rows, "raw": resp.text}

# ================= 메인 동작 =================
if st.button("급식 조회", type="primary"):
    with st.spinner("급식 정보를 불러오는 중..."):
        result = fetch_meal(yyyymmdd, verify_cert=verify_ssl)

    with st.expander("원문(JSON) 보기 (디버그)", expanded=False):
        st.code(result.get("raw", ""), language="json")

    if "error" in result:
        st.error(f"조회 실패: {result['error']}")
        if result.get("status") is not None:
            st.caption(f"HTTP 상태코드: {result['status']}")
    else:
        rows = result["rows"]
        if not rows:
            st.warning("해당 날짜의 급식 정보가 없습니다.")
        else:
            # 조식/중식/석식 정렬
            order = {"조식": 1, "중식": 2, "석식": 3}
            rows_sorted = sorted(rows, key=lambda r: order.get(r.get("MMEAL_SC_NM", ""), 99))

            for r in rows_sorted:
                meal_name = r.get("MMEAL_SC_NM", "-")
                kcal = r.get("CAL_INFO", "")
                dish_raw = r.get("DDISH_NM", "")
                origin = r.get("ORPLC_INFO", "")
                nutrients = r.get("NTR_INFO", "")

                dish_clean = clean_menu_text(
                    dish_raw,
                    drop_nums=remove_allergen_nums,
                    drop_paren_and_dots=remove_paren_and_dots
                )

                st.subheader(f"{meal_name} 🍽️")
                if kcal:
                    st.caption(f"열량: {kcal}")

                st.text_area(
                    "메뉴",
                    dish_clean if dish_clean else "(메뉴 정보 없음)",
                    height=180,
                    label_visibility="visible"
                )

                with st.expander("추가 정보 (원산지/영양)"):
                    st.markdown("**원산지**")
                    st.write(origin if origin else "(정보 없음)")
                    st.markdown("**영양정보**")
                    st.write(nutrients if nutrients else "(정보 없음)")

            st.success(f"{sel_date.strftime('%Y-%m-%d')} 급식 정보를 표시했습니다.")
else:
    st.info("날짜를 선택한 뒤 **`급식 조회`** 버튼을 누르세요.")
    st.caption("SSL 오류가 나면 사이드바의 'SSL 인증서 검사'를 꺼 보세요 (기본 OFF).")

# ================= 참고 스니펫(원본 로직) =================
with st.expander("참고: 원본 파이썬 로직 스니펫", expanded=False):
    st.code(
        '''
# 오늘 날짜 문자열 예시 (yyMMdd → 원본 방식)
현재 = str(datetime.datetime.now(pytz.timezone("Asia/Seoul")))
오늘 = 현재[2:4] + 현재[5:7] + 현재[8:10]

url = "https://open.neis.go.kr/hub/mealServiceDietInfo?ATPT_OFCDC_SC_CODE=B10&SD_SCHUL_CODE=7010806&Type=json&MLSV_YMD=" + 오늘
data = requests.get(url)
data_ = data.json()
target = data_['mealServiceDietInfo'][1]['row']
for row in target:
    dish_str = row['DDISH_NM']

클린1 = dish_str.replace("<br/>", "\\n")
클린2 = re.sub(r"\\d", "", 클린1)
최종 = 클린2.replace("(", "").replace(")", "").replace(".", "")
        ''',
        language="python"
    )
