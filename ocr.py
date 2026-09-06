import streamlit as st
import easyocr
import cv2
import numpy as np
import pandas as pd
from PIL import Image
import re

# 1. 페이지 설정
st.set_page_config(
    page_title="안성시 도서관 정배열 점검 시스템",
    page_icon="📚",
    layout="wide"
)

st.title("📚 안성시 도서관 스마트 정배열 점검 시스템")
st.write("책장 사진을 업로드하여 OCR을 수행하고, 도서관(LIS) 청구기호 기준 정배열 상태를 점검합니다.")

# 2. EasyOCR 모델을 st.cache_resource로 1회만 로드 (CPU 환경 최적화)
@st.cache_resource
def load_ocr_reader():
    return easyocr.Reader(['ko', 'en'], gpu=False)

with st.spinner("AI OCR 모델을 불러오는 중입니다... 잠시만 기다려주세요."):
    reader = load_ocr_reader()

# 세션 상태(Session State) 초기화 (버튼을 눌러도 OCR이 재실행되지 않도록 분리)
if "extracted_results" not in st.session_state:
    st.session_state["extracted_results"] = None
if "raw_texts" not in st.session_state:
    st.session_state["raw_texts"] = []

# --- [기능 함수 정의] ---
def clean_call_number(text):
    """청구기호 문자열 정제 및 복본(c.1, c.2 등) 표기 추출"""
    text = text.strip()
    # 복본 번호 추출 (예: c.1, c.2, cop.1 등)
    copy_match = re.search(r'(?:c\.?|cop\.?)\s*(\d+)', text, re.IGNORECASE)
    copy_num = int(copy_match.group(1)) if copy_match else 1
    return text, copy_num

def parse_classification(text):
    """LIS 청구기호 분류기호(숫자/KDC 등) 추출 파서"""
    match = re.search(r'(\d+(?:\.\d+)?)', text)
    if match:
        return float(match.group(1))
    return 0.0

# 3. 파일 업로더 생성
uploaded_file = st.file_uploader(
    "책장 사진을 선택하세요 (PNG, JPG, JPEG)", 
    type=["png", "jpg", "jpeg"]
)

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("업로드된 책장 사진")
        st.image(image, width='stretch')

    with col2:
        st.subheader("1단계: OCR 텍스트 추출")
        
        # OCR 실행 버튼 (정배열 점검과 완전히 분리)
        if st.button("OCR 텍스트 추출 실행", type="secondary"):
            try:
                with st.spinner("이미지에서 텍스트를 추출하는 중입니다..."):
                    img_array = np.array(image)
                    if len(img_array.shape) == 3 and img_array.shape[2] == 3:
                        img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
                    
                    # OCR 수행
                    results = reader.readtext(img_array)
                    
                    if not results:
                        st.warning("이미지에서 텍스트를 감지하지 못했습니다.")
                        st.session_state["extracted_results"] = None
                    else:
                        st.session_state["extracted_results"] = results
                        st.session_state["raw_texts"] = [text for (_, text, _) in results]
                        st.success("OCR 텍스트 추출이 완료되었습니다!")
            except Exception as e:
                # OCR 실패 시 오류 원인을 화면에 구체적으로 표시
                st.error(f"OCR 처리 중 오류가 발생했습니다.\n\n**오류 내용**: {str(e)}")
                st.session_state["extracted_results"] = None

        # 추출된 텍스트가 있는 경우 화면에 표시
        if st.session_state["extracted_results"]:
            full_text = "\n".join(st.session_state["raw_texts"])
            st.text_area("추출된 원본 텍스트 목록", full_text, height=150)

    # 4. 2단계: 정배열 점검 실행 (OCR 결과가 있을 때만 활성화, OCR 재실행 없음)
    if st.session_state["extracted_results"]:
        st.markdown("---")
        st.subheader("2단계: LIS 기반 정배열 점검")
        st.write("추출된 청구기호를 바탕으로 도서관 배열 순서 및 오배가 여부를 판정합니다.")

        if st.button("정배열 점검 실행", type="primary"):
            with st.spinner("정배열 상태를 분석 중입니다..."):
                raw_data = st.session_state["raw_texts"]
                
                parsed_items = []
                for idx, text in enumerate(raw_data):
                    cleaned_text, copy_num = clean_call_number(text)
                    class_num = parse_classification(cleaned_text)
                    parsed_items.append({
                        "순서": idx + 1,
                        "추출된 청구기호": cleaned_text,
                        "분류기호값": class_num,
                        "복본번호": copy_num
                    })
                
                df = pd.DataFrame(parsed_items)
                
                if not df.empty:
                    # LIS 기준 정렬 판정 (분류기호 기준 오름차순, 동일할 경우 복본번호 기준)
                    df['정렬기준'] = list(zip(df['분류기호값'], df['복본번호']))
                    df['이전값'] = df['정렬기준'].shift(1)
                    
                    # 오배가 판정 로직 (이전 도서보다 분류기호가 작아지는 경우 오배가 의심)
                    def check_misplacement(row):
                        if pd.isna(row['이전값']):
                            return "시작 도서"
                        # 분류기호가 역전되었는지 확인
                        if row['분류기호값'] < row['이전값'][0]:
                            return "⚠️ 오배가 의심"
                        elif row['분류기호값'] == row['이전값'][0] and row['복본번호'] < row['이전값'][1]:
                            return "⚠️ 복본 순서 오류"
                        elif row['분류기호값'] == row['이전값'][0] and row['복본번호'] == row['이전값'][1]:
                            return "🔄 동일 도서(중복)"
                        return "정상 배열"

                    df['상태'] = df.apply(check_misplacement, axis=1)
                    
                    # 정배열 유지율 계산 (정상 배열 및 시작 도서 비율)
                    total_books = len(df)
                    normal_books = len(df[df['상태'].isin(["시작 도서", "정상 배열"])])
                    retention_rate = (normal_books / total_books) * 100 if total_books > 0 else 0
                    
                    # 결과 지표 출력
                    col_m1, col_m2 = st.columns(2)
                    col_m1.metric("총 인식 도서 수", f"{total_books}권")
                    col_m2.metric("정배열 유지율", f"{retention_rate:.1f}%")
                    
                    # 결과 테이블 정리 (불필요한 임시 컬럼 제거)
                    display_df = df[['순서', '추출된 청구기호', '복본번호', '상태']].copy()
                    
                    st.dataframe(display_df, width='stretch')
                    
                    # CSV 결과 다운로드 추가
                    csv_data = display_df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        label="점검 결과 CSV 다운로드",
                        data=csv_data,
                        file_name="library_shelf_audit_result.csv",
                        mime="text/csv"
                    )
                else:
                    st.info("분석할 청구기호 데이터가 부족합니다.")
