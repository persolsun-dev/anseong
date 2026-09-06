import streamlit as st
import easyocr
import cv2
import numpy as np
from PIL import Image

# 1. 페이지 설정
st.set_page_config(
    page_title="안성시 OCR 서비스",
    page_icon="🤖",
    layout="wide"
)

st.title("📄 안성시 문서 OCR (문자 인식) 시스템")
st.write("이미지를 업로드하면 텍스트를 자동으로 추출해 줍니다.")

# 2. OCR 모델을 캐싱하여 한 번만 로드하고 재사용 (메모리 폭발 및 반복 다운로드 방지)
@st.cache_resource
def load_ocr_reader():
    # CPU 환경에서 한국어와 영어를 인식하도록 설정
    return easyocr.Reader(['ko', 'en'], gpu=False)

# 모델 로딩 상태 표시
with st.spinner("AI OCR 모델을 불러오는 중입니다... 잠시만 기다려주세요."):
    reader = load_ocr_reader()

# 3. 파일 업로더 생성
uploaded_file = st.file_uploader(
    "이미지 파일을 선택하세요 (PNG, JPG, JPEG)", 
    type=["png", "jpg", "jpeg"]
)

if uploaded_file is not None:
    # 이미지 읽기
    image = Image.open(uploaded_file)
    
    # 레이아웃 분할 (좌우 화면)
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("업로드된 원본 이미지")
        # 최신 Streamlit 표준 속성인 width='stretch' 사용
        st.image(image, width='stretch')

    with col2:
        st.subheader("OCR 인식 결과")
        
        if st.button("텍스트 추출 시작", type="primary"):
            with st.spinner("텍스트를 분석 중입니다..."):
                # PIL Image를 OpenCV 형식(numpy array)으로 변환
                img_array = np.array(image)
                
                # 이미지 채널 변환 (RGB -> BGR)
                if len(img_array.shape) == 3 and img_array.shape[2] == 3:
                    img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
                
                # OCR 실행
                results = reader.readtext(img_array)
                
                # 결과 추출 및 출력
                extracted_text = []
                for (bbox, text, prob) in results:
                    extracted_text.append(text)
                
                full_text = "\n".join(extracted_text)
                
                if full_text.strip():
                    st.success("추출 완료!")
                    st.text_area("추출된 텍스트", full_text, height=200)
                    
                    # 다운로드 버튼 제공
                    st.download_button(
                        label="결과 텍스트 파일 저장",
                        data=full_text,
                        file_name="ocr_result.txt",
                        mime="text/plain"
                    )
                else:
                    st.warning("이미지에서 인식된 텍스트가 없습니다.")
