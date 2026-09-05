import csv
import io
import os
import platform
import re
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import List
import unicodedata

# 표준 한글 초성 순서 리스트
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
    """한글 NFC 정규화 및 공백 제거"""
    if not text:
        return ""
    return unicodedata.normalize("NFC", str(text)).strip()


def text_to_sort_key(text: str):
    """단일 자음과 완성형 음절을 표준 한글 자모(초성) 순서에 맞춰 정렬 키로 변환"""
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
    """
    청구기호 분석 파서:
    1. 분류기호: 실수형 수치 비교 (0, float)
    2. 저자기호 영역:
       - 단축기호(예: 나15)가 확장기호(나15-2)보다 앞에 오도록 가중치 부여
       - 하이픈(-) 및 숫자는 자음(ㅅ)보다 우선 정렬되도록 순위 조정
    3. 권차/부기호 영역: 정수 크기 비교(0, int)
    """
    call_num = normalize_text(call_num)
    if not call_num:
        return ()

    # 복본(c.) 분리
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
        # 1. 분류기호 (첫 번째 토큰이 수치인 경우)
        if idx == 0 and re.match(r"^\d+(\.\d+)?$", token):
            key_list.append((0, float(token)))
            continue

        # 2. 저자기호 영역 (두 번째 토큰)
        if idx == 1:
            sub_tokens = re.findall(r"\d+|\D+", token)
            for p in sub_tokens:
                if p.isdigit():
                    key_list.append((1, p))
                elif p == "-":
                    # 하이픈은 자음보다 앞서고 단축기호보다는 뒤에 오도록 가중치 1 부여
                    key_list.append((1, "-"))
                else:
                    # 한글/문자 부호는 가중치 2 부여
                    key_list.append((2, text_to_sort_key(p)))
            # 토큰 끝에 도달했을 때 단축기호가 확장기호보다 먼저 오도록 기본 종료 마커 추가
            key_list.append((0, "END"))
            continue

        # 3. 권차, 부기호 및 하이픈이 포함된 토큰 처리 (세 번째 토큰 이후)
        sub_tokens = re.findall(r"\d+|\D+", token)
        for p in sub_tokens:
            if p.isdigit():
                key_list.append((0, int(p)))
            elif p == "-":
                key_list.append((1, "-"))
            else:
                key_list.append((2, text_to_sort_key(p)))

    # 4. 복본기호 처리
    if copy_num:
        if copy_num.isdigit():
            key_list.append((0, int(copy_num)))
        else:
            key_list.append((2, text_to_sort_key(copy_num)))

    return tuple(key_list)


def run_vba_oneclick_inspection(original_data: List[str]):
    cleaned_data = [
        normalize_text(x) for x in original_data if normalize_text(x)
    ]
    if not cleaned_data:
        return {
            "results": [],
            "statistics": {
                "점검대상건수": 0,
                "정배열건수": 0,
                "오류도서건수": 0,
                "C열에없음": 0,
                "G빈값": 0,
                "정확도": 0.0,
            },
        }

    var_g = list(cleaned_data)

    # 1. 정렬 파싱 키 생성
    indexed_data = []
    for idx, item in enumerate(cleaned_data):
        key = parse_call_number(item)
        indexed_data.append((idx, item, key))

    # 2. 파싱 키 기반 커스텀 정렬
    def custom_sort_key(item):
        return (item[2], item[0])

    sorted_data = sorted(indexed_data, key=custom_sort_key)

    var_c = [item[1] for item in sorted_data]

    last_c = len(var_c)
    last_g = len(var_g)
    last_row = max(last_c, last_g)

    # 3. dictC 생성
    dict_c = {}
    for i in range(last_c):
        val = var_c[i]
        if val != "":
            dict_c[val] = i + 1

    # 4. G열 연속 그룹화
    group_start = []
    group_end = []
    group_val = []

    i = 0
    while i < last_g:
        g_val = var_g[i]
        if g_val != "" and g_val in dict_c:
            g_start_idx = i + 1
            g_dict_val = dict_c[g_val]

            k = i
            while k + 1 < last_g:
                if var_g[k + 1] == g_val:
                    k += 1
                else:
                    break
            g_end_idx = k + 1

            group_start.append(g_start_idx)
            group_end.append(g_end_idx)
            group_val.append(g_dict_val)

            i = k + 1
        else:
            i += 1

    g_count = len(group_val)

    # 5. LIS 알고리즘 (최장 공통 부분 수열)
    keep_group = set()
    if g_count > 0:
        tails = [0] * (g_count + 1)
        tail_indices = [0] * (g_count + 1)
        prev = [0] * (g_count + 1)
        lis_len = 0

        for i_idx in range(1, g_count + 1):
            val = group_val[i_idx - 1]
            low = 1
            high = lis_len

            while low <= high:
                mid_pt = (low + high) // 2
                if tails[mid_pt] <= val:
                    low = mid_pt + 1
                else:
                    high = mid_pt - 1

            pos = low
            tails[pos] = val
            tail_indices[pos] = i_idx

            if pos > 1:
                prev[i_idx] = tail_indices[pos - 1]
            else:
                prev[i_idx] = 0

            if pos > lis_len:
                lis_len = pos

        curr = tail_indices[lis_len]
        while curr != 0:
            keep_group.add(curr)
            curr = prev[curr]

    # 6. 최종 매핑 및 판정
    group_idx_map = [0] * (last_row + 1)
    for idx in range(g_count):
        for j_idx in range(group_start[idx], group_end[idx] + 1):
            group_idx_map[j_idx] = idx + 1

    results = []
    total_count = 0
    correct_count = 0
    c_missing_count = 0
    g_empty_count = 0

    for idx in range(1, last_row + 1):
        g_item = var_g[idx - 1] if idx - 1 < len(var_g) else ""

        if g_item == "":
            status = "G빈값"
            g_empty_count += 1
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
            "C열에없음": c_missing_count,
            "G빈값": g_empty_count,
            "정확도": accuracy,
        },
    }


class SmartShelfApp:

    def __init__(self, root):
        self.root = root
        self.root.title("SmartShelf AI - 서가 정배열 점검")
        self.root.geometry("1100x720")
        self.root.minsize(900, 600)

        self.result = None
        self.create_ui()

    def create_ui(self):
        header = ttk.Frame(self.root, padding=15)
        header.pack(fill="x")

        ttk.Label(
            header, text="SmartShelf AI", font=("맑은 고딕", 24, "bold")
        ).pack(side="left")

        ttk.Label(
            header,
            text="  서가 정배열 점검 시스템",
            font=("맑은 고딕", 12),
        ).pack(side="left", pady=(8, 0))

        input_frame = ttk.LabelFrame(
            self.root, text="① 서가 데이터 입력", padding=12
        )
        input_frame.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        ttk.Label(
            input_frame,
            text=(
                "청구기호를 실제 서가에 꽂혀 있는 순서대로 한 줄에 하나씩"
                " 입력하세요."
            ),
        ).pack(anchor="w")

        self.text = tk.Text(
            input_frame, font=("맑은 고딕", 12), wrap="none", height=8
        )
        self.text.pack(fill="both", expand=True, pady=8)

        button_frame = ttk.Frame(self.root, padding=(15, 5))
        button_frame.pack(fill="x")

        ttk.Button(
            button_frame, text="정배열 점검 실행", command=self.run_inspection
        ).pack(side="left", padx=(0, 8))

        ttk.Button(
            button_frame, text="파일에서 불러오기", command=self.load_file
        ).pack(side="left", padx=8)

        ttk.Button(
            button_frame, text="결과 저장", command=self.save_result
        ).pack(side="left", padx=8)

        ttk.Button(
            button_frame, text="입력 초기화", command=self.clear_input
        ).pack(side="left", padx=8)

        result_frame = ttk.LabelFrame(
            self.root, text="② 점검 결과", padding=10
        )
        result_frame.pack(fill="both", expand=True, padx=15, pady=(5, 15))

        self.summary = ttk.Label(
            result_frame,
            text="정배열 점검 실행 버튼을 눌러주세요.",
            font=("맑은 고딕", 13, "bold"),
        )
        self.summary.pack(anchor="w", pady=(0, 8))

        tree_container = ttk.Frame(result_frame)
        tree_container.pack(fill="both", expand=True)

        tree_container.columnconfigure(0, weight=1)
        tree_container.rowconfigure(0, weight=1)

        columns = ("번호", "청구기호", "판정")
        self.tree = ttk.Treeview(
            tree_container, columns=columns, show="headings"
        )

        self.tree.tag_configure(
            "error", background="#FFEBEE", foreground="#C62828"
        )
        self.tree.tag_configure(
            "missing", background="#FFF3E0", foreground="#E65100"
        )
        self.tree.tag_configure("correct", foreground="#2E7D32")

        self.tree.heading("번호", text="번호")
        self.tree.heading("청구기호", text="청구기호")
        self.tree.heading("판정", text="판정")

        self.tree.column("번호", width=80, anchor="center")
        self.tree.column("청구기호", width=550)
        self.tree.column("판정", width=180, anchor="center")

        scrollbar = ttk.Scrollbar(
            tree_container, orient="vertical", command=self.tree.yview
        )

        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

    def run_inspection(self):
        raw_text = self.text.get("1.0", "end")
        raw_lines = raw_text.splitlines()
        books = [x for x in raw_lines if x.strip()]

        if not books:
            messagebox.showwarning("입력 필요", "청구기호를 입력해주세요.")
            return

        self.result = run_vba_oneclick_inspection(books)

        for item in self.tree.get_children():
            self.tree.delete(item)

        for r in self.result["results"]:
            status = r["status"]
            if status == "오류도서":
                tag = "error"
                disp_status = "오류도서"
            elif status == "C열에 없음":
                tag = "missing"
                disp_status = "C열에 없음"
            elif status == ".":
                tag = "correct"
                disp_status = "정배열"
            else:
                tag = ""
                disp_status = status

            self.tree.insert(
                "",
                "end",
                values=(r["index"] + 1, r["call_number"], disp_status),
                tags=(tag,),
            )

        s = self.result["statistics"]
        self.summary.config(
            text=(
                f"점검 {s['점검대상건수']}건  |  "
                f"정배열 {s['정배열건수']}건  |  "
                f"오류 {s['오류도서건수']}건  |  "
                f"정확도 {s['정확도']:.2f}%"
            )
        )

        self.root.update_idletasks()

    def load_file(self):
        path = filedialog.askopenfilename(
            title="청구기호 파일 선택",
            filetypes=[
                ("지원 파일 (*.txt, *.csv)", "*.txt;*.csv"),
                ("텍스트 파일", "*.txt"),
                ("CSV 파일", "*.csv"),
                ("모든 파일", "*.*"),
            ],
        )

        if not path:
            return

        content = ""
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                with open(path, "r", encoding="cp949") as f:
                    content = f.read()
            except Exception as e:
                messagebox.showerror("파일 오류", str(e))
                return
        except Exception as e:
            messagebox.showerror("파일 오류", str(e))
            return

        extracted_lines = []
        if path.lower().endswith(".csv") or "," in content:
            reader = csv.reader(io.StringIO(content))
            for row in reader:
                if row:
                    for cell in row:
                        val = cell.strip()
                        if val:
                            extracted_lines.append(val)
                            break
            final_text = "\n".join(extracted_lines)
        else:
            final_text = content

        self.text.delete("1.0", "end")
        self.text.insert("1.0", final_text)

    def save_result(self):
        if self.result is None:
            messagebox.showwarning(
                "저장할 결과 없음", "먼저 정배열 점검을 실행해주세요."
            )
            return

        path = filedialog.asksaveasfilename(
            title="결과 저장",
            defaultextension=".txt",
            filetypes=[("텍스트 파일", "*.txt")],
        )

        if not path:
            return

        try:
            s = self.result["statistics"]
            with open(path, "w", encoding="utf-8-sig") as f:
                f.write("SmartShelf AI - 서가 정배열 점검 결과\n")
                f.write("=" * 60 + "\n\n")
                f.write(f"점검대상건수: {s['점검대상건수']}\n")
                f.write(f"정배열건수: {s['정배열건수']}\n")
                f.write(f"오류도서건수: {s['오류도서건수']}\n")
                f.write(f"정확도: {s['정확도']:.2f}%\n\n")
                f.write("[상세 결과]\n")

                for r in self.result["results"]:
                    f.write(
                        f"{r['index'] + 1}\t{r['call_number']}\t{r['status']}\n"
                    )

            messagebox.showinfo("저장 완료", "점검 결과를 저장했습니다.")
        except Exception as e:
            messagebox.showerror("저장 오류", str(e))

    def clear_input(self):
        if not messagebox.askyesno("초기화", "입력 내용을 모두 지울까요?"):
            return

        self.text.delete("1.0", "end")

        for item in self.tree.get_children():
            self.tree.delete(item)

        self.summary.config(text="정배열 점검 실행 버튼을 눌러주세요.")
        self.result = None


def main():
    root = tk.Tk()
    app = SmartShelfApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()