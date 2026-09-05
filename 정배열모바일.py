import io
import re
import unicodedata
import cv2
import easyocr
import numpy as np
import streamlit as st

# 페이지 설정 (모바일 최적화 레이아웃)
st.set_page_config(
    page_title="SmartShelf 모바일 서가 점검", page_icon="📚", layout="centered"
)

# ---------------------------------------------------------
# 1. OCR 모델 캐싱 (앱 실행 시 한 번만 로드하여 속도 향상)
# ---------------------------------------------------------


@st.cache_resource
def get_ocr_reader():
    return easyocr.Reader(["ko", "en"], gpu=False)


# ---------------------------------------------------------
# 2. 청구기호 정렬 및 파싱 알고리즘
# ---------------------------------------------------------
CHOSEONGS = [
    "ㄱ",
    "ㄲ",
    "ㄴ",
    "ㄷ",
    "ㄸ",
    "ㄹ",
    "ㅁ",
    "ㅂ",
    "ㅃ",
    "ㅅ",
    "ㅆ",
    "ㅇ",
    "ㅈ",
    "ㅉ",
    "ㅊ",
    "ㅋ",
    "ㅌ",
    "ㅍ",
    "ㅎ",
]
CHOSEONG_MAP = {ch: i for i, ch in enumerate(CHOSEONGS)}


def normalize_text(text: str) -> str:
    if not text:
        return ""
    return unicodedata.normalize("NFC", str(text)).strip()


def text_to_sort_key(text: str):
    char_keys = []
    for ch in text:
        if ch in CHOSEONG_MAP:
            char_keys.append((CHOSEONG_MAP[ch], 0, 0, 0))
        elif 0xAC00 <= ord(ch) <= 0xD7A3:
            code = ord(ch) - 0xAC00
            cho = code // (21 * 28)
            jung = (code % (21 * 28)) // 28
            jong = code % 28
            char_keys.append((cho, 1, jung, jong))
        else:
            char_keys.append((999, ord(ch), 0, 0))
    return tuple(char_keys)


def parse_call_number(call_num: str):
    call_num = normalize_text(call_num)
    if not call_num:
        return ()

    c_pos = call_num.lower().rfind(" c.")
    copy_num = ""
    if c_pos >= 0:
        copy_num = call_num[c_pos + 3 :].strip()
        call_num = call_num[:c_pos].strip()

    tokens = call_num.split()
    if not tokens:
        return ()

    key_list = []
    for idx, token in enumerate(tokens):
        if idx == 0 and re.match(r"^\d+(\.\d+)?$", token):
            key_list.append((0, float(token)))
            continue

        if idx == 1:
            sub_tokens = re.findall(r"\d+|\D+", token)
            for p in sub_tokens:
                if p.isdigit():
                    key_list.append((1, p))
                elif p == "-":
                    key_list.append((1, "-"))
                else:
                    key_list.append((2, text_to_sort_key(p)))
            key_list.append((0, "END"))
            continue

        sub_tokens = re.findall(r"\d+|\D+", token)
        for p in sub_tokens:
            if p.isdigit():
                key_list.append((0, int(p)))
            elif p == "-":
                key_list.append((1, "-"))
            else:
                key_list.append((2, text_to_sort_key(p)))

    if copy_num:
        if copy_num.isdigit():
            key_list.append((0, int(copy_num)))
        else:
            key_list.append((2, text_to_sort_key(copy_num)))

    return tuple(key_list)


def run_vba_oneclick_inspection(original_data):
    cleaned_data = [
        normalize_text(x) for x in original_data if normalize_text(x)
    ]
    if not cleaned_data:
        return {"results": [], "statistics": {}}

    var_g = list(cleaned_data)
    indexed_data = [
        (idx, item, parse_call_number(item))
        for idx, item in enumerate(cleaned_data)
    ]
    sorted_data = sorted(indexed_data, key=lambda x: (x[2], x[0]))
    var_c = [item[1] for item in sorted_data]

    last_c, last_g = len(var_c), len(var_g)
    last_row = max(last_c, last_g)

    dict_c = {val: i + 1 for i, val in enumerate(var_c) if val != ""}

    group_start, group_end, group_val = [], [], []
    i = 0
    while i < last_g:
        g_val = var_g[i]
        if g_val != "" and g_val in dict_c:
            g_start_idx = i + 1
            g_dict_val = dict_c[g_val]
            k = i
            while k + 1 < last_g and var_g[k + 1] == g_val:
                k += 1
            group_start.append(g_start_idx)
            group_end.append(k + 1)
            group_val.append(g_dict_val)
            i = k + 1
        else:
            i += 1

    g_count = len(group_val)
    keep_group = set()
    if g_count > 0:
        tails, tail_indices, prev = (
            [0] * (g_count + 1),
            [0] * (g_count + 1),
            [0] * (g_count + 1),
        )
        lis_len = 0
        for i_idx in range(1, g_count + 1):
            val = group_val[i_idx - 1]
            low, high = 1, lis_len
            while low <= high:
                mid = (low + high) // 2
                if tails[mid] <= val:
                    low = mid + 1
                else:
                    high = mid - 1
            pos = low
            tails[pos], tail_indices[pos] = val, i_idx
            prev[i_idx] = tail_indices[pos - 1] if pos > 1 else 0
            if pos > lis_len:
                lis_len = pos
        curr = tail_indices[lis_len]
        while curr != 0:
            keep_group.add(curr)
            curr = prev[curr]

    group_idx_map = [0] * (last_row + 1)
    for idx in range(g_count):
        for j_idx in range(group_start[idx], group_end[idx] + 1):
            group_idx_map[j_idx] = idx + 1

    results, total_count, correct_count, c_missing_count = [], 0, 0, 0
    for idx in range(1, last_row + 1):
        g_item = var_g[idx - 1] if idx - 1 < len(var_g) else ""
        if g_item == "":
            status = "G빈값"
        else:
            total_count += 1
            if g_item not in dict_c:
                status = "C열에 없음"
                c_missing_count += 1
            else:
                g_idx = group_idx_map[idx]
                if g_idx > 0 and g_idx in keep_group:
                    status = "."
                    correct_count += 1
                else:
                    status = "오류도서"
        results.append(
            {"index": idx - 1, "call_number": g_item, "status": status}
        )

    accuracy = (
        round((correct_count / total_count * 100), 2) if total_count > 0 else 0.0
    )
    return {
        "results": results,
        "statistics": {
            "점검대상건수": total_count,
            "정배열건수": correct_count,
            "오류도서건수": total_count - correct_count - c_missing_count,
            "정확도": accuracy,
        },
    }


# ---------------------------------------------------------
# 3. Streamlit 모바일 웹 UI 구성
# ---------------------------------------------------------
st.title("📚 SmartShelf 모바일 점검")
st.write("스마트폰 카메라로 서가 책등을 촬영해 즉시 오배가를 확인하세요.")

camera_file = st.camera_input("서가 책등 촬영하기")
uploaded_file = st.file_uploader(
    "또는 갤러리에서 사진 업로드", type=["jpg", "jpeg", "png"]
)

target_image = camera_file if camera_file else uploaded_file

if target_image is not None:
    bytes_data = target_image.getvalue()
    np_arr = np.frombuffer(bytes_data, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    st.image(
        target_image, caption="촬영된 서가 이미지", use_container_width=True
    )

    with st.spinner("AI가 청구기호를 인식하는 중입니다..."):
        reader = get_ocr_reader()
        ocr_results = reader.readtext(img)
        sorted_ocr = sorted(ocr_results, key=lambda x: x[0][0][1])
        detected_lines = [res[1] for res in sorted_ocr if res[2] > 0.3]

    st.subheader("📝 인식된 청구기호 목록 (수정 가능)")
    st.info(
        "OCR 인식 특성상 오인식된 글자가 있을 수 있습니다. 아래 텍스트 상자에서"
        " 직접 수정 후 점검을 실행하세요."
    )

    default_text_content = "\n".join(detected_lines)
    edited_text = st.text_area(
        "청구기호 편집", value=default_text_content, height=150
    )

    if st.button("정배열 점검 실행", type="primary", use_container_width=True):
        books = [line.strip() for line in edited_text.splitlines() if line.strip()]
        if books:
            inspection_res = run_vba_oneclick_inspection(books)
            s = inspection_res["statistics"]

            st.metric(
                label="정배열 정확도",
                value=f"{s['정확도']}%",
                delta=f"정상 {s['정배열건수']} / 오류 {s['오류도서건수']}",
            )

            st.subheader("🔍 점검 상세 결과")
            for r in inspection_res["results"]:
                status = r["status"]
                call_num = r["call_number"]
                if status == ".":
                    st.success(f"{r['index'] + 1}. {call_num} (정배열)")
                elif status == "오류도서":
                    st.error(f"❌ {r['index'] + 1}. {call_num} (오배가 의심)")
                else:
                    st.warning(f"⚠️ {r['index'] + 1}. {call_num} ({status})")
        else:
            st.warning("점검할 청구기호가 없습니다.")