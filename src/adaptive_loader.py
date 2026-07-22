# -*- coding: utf-8 -*-
"""
적응형 계정별원장 로더
------------------------------------------------------------
회사·회계시스템마다 형식이 달라도(시트별형/단일표형, 열 이름·순서·날짜형식 상이)
'표준 원장'으로 통일해 주는 만능 로더.

핵심 전략:
  1) 모든 형식에 공통으로 존재하는 '차변/대변 헤더 행'을 앵커로 찾는다.
  2) 열을 '위치'가 아니라 '이름(키워드)'으로 매칭한다.
  3) 거래행 = '날짜가 실제 날짜로 파싱되는 행' → 이월/누계/소계는 자동 제외.
  4) 계정코드/계정명은 (열 → 시트명 → 머리글 셀) 순으로 유연 인식.
  실패 시 명확한 사유와 함께 예외를 던진다(배치 실행기가 격리).

표준 출력 스키마:
  계정코드 · 계정명 · 전표일자 · 적요 · 거래처명 · 차변 · 대변 · 잔액
"""
import re
import numpy as np
import pandas as pd
from pathlib import Path

STD_COLS = ["계정코드", "계정명", "전표일자", "적요", "거래처명", "차변", "대변", "잔액"]


def norm(x):
    return re.sub(r"\s+", "", str(x))


def infer_year(name):
    m = re.search(r"(20\d\d)", name)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d\d)\s*년", name)
    if m:
        return 2000 + int(m.group(1))
    return 2025


def find_header_row(raw):
    """앞 15행 중 '차변&대변'을 포함하고 키워드가 가장 많은 행 = 헤더."""
    KW = ["차변", "대변", "적요", "일자", "날짜", "회계일", "계정", "거래처", "잔액"]
    best, best_s = None, 0
    for i in range(min(15, len(raw))):
        vals = [norm(v) for v in raw.iloc[i].tolist()]
        has_dc = any("차변" in v for v in vals) and any("대변" in v for v in vals)
        if not has_dc:
            continue
        score = sum(any(k in v for k in KW) for v in vals)
        if score > best_s:
            best, best_s = i, score
    return best


def _find(cols, includes, excludes=()):
    for key in includes:
        for i, h in enumerate(cols):
            if key in h and not any(e in h for e in excludes):
                return i
    return None


def build_colmap(cols):
    """정규화된 헤더 리스트 → 표준 필드별 열 인덱스."""
    cm = {}
    # 날짜 후보(파싱 성공률로 뒤에서 확정)
    DKW = ["전표일자", "회계일", "거래일자", "일자", "날짜"]
    cm["date_cands"] = [i for i, h in enumerate(cols)
                        if any(k in h for k in DKW)
                        and not any(x in h for x in ["일시", "예정일", "기표일", "입력일", "수정일"])]
    cm["debit"] = _find(cols, ["차변"], ["외화"])
    cm["credit"] = _find(cols, ["대변"], ["외화"])
    cm["balance"] = _find(cols, ["잔액"])
    # 적요: 정확히 '적요' 우선(적요2 회피)
    cm["memo"] = next((i for i, h in enumerate(cols) if h == "적요"), None)
    if cm["memo"] is None:
        cm["memo"] = _find(cols, ["적요", "내용"])
    cm["acctcode"] = _find(cols, ["계정과목코드", "계정코드"])
    cm["acctname"] = _find(cols, ["계정과목명", "계정명"])
    if cm["acctname"] is None:
        cm["acctname"] = _find(cols, ["계정과목"], ["코드"])
    cm["cp"] = _find(cols, ["거래처명", "거래처전명", "거래처"], ["코드"])
    cm["docno"] = _find(cols, ["전표번호", "전표기표번호", "기표번호", "승인번호"], ["라인"])
    # FR-13 메타필드(있을 때만 — 부정 레드플래그 강화용). 없으면 None → 관련 플래그 자동 생략.
    cm["author"] = _find(cols, ["작성자", "입력자", "기표자", "등록자", "결재자"], ["코드", "거래처"])
    cm["inputdate"] = _find(cols, ["입력일", "작성일", "기표일", "등록일", "입력일시", "기표일시"])
    cm["jtype"] = _find(cols, ["전표유형", "전표종류", "전표구분", "입력구분", "작성구분",
                               "수기여부", "입력방법", "전표형태"], ["번호"])
    return cm


# Excel serial date(1899-12-30 기준 일수)로 인정할 범위 — 1990-01-01 ~ 2079-12-31.
# 이 범위를 벗어난 숫자(금액 등)는 날짜로 보지 않는다.
_SERIAL_MIN, _SERIAL_MAX = 32874, 65746


def parse_dates(s, year):
    out = pd.to_datetime(s, errors="coerce")
    # 숫자로 들어온 Excel serial date 보정.
    # pd.to_datetime은 숫자를 '1970 기준 나노초'로 해석해 전부 1970-01-01이 되므로,
    # 합리적 범위의 순수 숫자만 골라 Excel 기준일(1899-12-30)로 다시 계산한다.
    nums = pd.to_numeric(s, errors="coerce")
    serial = nums.notna() & nums.between(_SERIAL_MIN, _SERIAL_MAX)
    if serial.any():
        out.loc[serial] = pd.to_datetime(nums[serial], unit="D", origin="1899-12-30")
    strs = s.astype(str).str.strip()
    md = strs.str.match(r"^\d{1,2}[-/.]\d{1,2}$")     # 연도 없는 MM-DD
    if md.any():
        fixed = (f"{year}-" + strs[md].str.replace(r"[/.]", "-", regex=True))
        out.loc[md] = pd.to_datetime(fixed, errors="coerce")
    return out


def resolve_acct(sheet, raw):
    """시트명 또는 머리글 셀에서 (계정코드, 계정명) 추출."""
    m = re.search(r"\((\d{5,10})\)", sheet)           # (010800), (1010000)
    if m:
        code = m.group(1)
        name = re.sub(r"\(\d{5,10}\)", "", re.sub(r"^\d+_", "", sheet)).strip()
        return code, name
    m = re.match(r"^(\d{5,10})\s*(.+)$", sheet)        # 11100105보통예금
    if m:
        return m.group(1), m.group(2).strip()
    # 시트명에 코드 없음 → 머리글 셀에서 '계정과목 : 1030000' 탐색
    for i in range(min(6, len(raw))):
        for cell in raw.iloc[i].tolist():
            mm = re.search(r"계정과목\s*:\s*(\d{5,10})", str(cell))
            if mm:
                return mm.group(1), sheet.strip()
    return None, sheet.strip()


def _to_num(s):
    return pd.to_numeric(s, errors="coerce")


def _std_from_sheet(sheet, raw, hr, cm, year, use_acct_cols):
    data = raw.iloc[hr + 1:].reset_index(drop=True)
    dcol = cm["date"]
    dates = parse_dates(data.iloc[:, dcol], year)
    mask = dates.notna()
    # 대괄호 소계/이월 행 제외 (예: [전기이월] [월계] [누계] [합계]) — 정상 적요('전기요금' 등)는 안 걸림
    if cm["memo"] is not None:
        mn = data.iloc[:, cm["memo"]].map(norm)
        subtotal = mn.str.match(r"\[[^\]]*(이월|누계|월계|합계|소계)[^\]]*\]").fillna(False)
        mask = mask & ~subtotal
    tx = data[mask]
    if tx.empty:
        return None, (0.0, 0.0)

    D = _to_num(tx.iloc[:, cm["debit"]]).fillna(0)
    C = _to_num(tx.iloc[:, cm["credit"]]).fillna(0)
    memo = tx.iloc[:, cm["memo"]].astype(str).str.strip() if cm["memo"] is not None else ""
    cp = tx.iloc[:, cm["cp"]] if cm["cp"] is not None else np.nan
    bal = _to_num(tx.iloc[:, cm["balance"]]) if cm["balance"] is not None else np.nan
    docno = (tx.iloc[:, cm["docno"]].astype(str).str.strip()
             if cm.get("docno") is not None else "")

    if use_acct_cols and cm["acctcode"] is not None:
        code = tx.iloc[:, cm["acctcode"]].astype(str).str.strip()
        name = (tx.iloc[:, cm["acctname"]].astype(str).str.strip()
                if cm["acctname"] is not None else code)
    elif use_acct_cols and cm["acctname"] is not None:
        name = tx.iloc[:, cm["acctname"]].astype(str).str.strip()
        code = name                         # 코드 열 없음 → 계정명을 임시 코드로(뒤에서 합성 숫자코드로 치환)
    else:
        c, n = resolve_acct(sheet, raw)
        code = pd.Series(c, index=tx.index)
        name = pd.Series(n, index=tx.index)

    std = pd.DataFrame({"계정코드": code, "계정명": name,
                        "전표일자": dates[mask].values, "전표번호": docno, "적요": memo,
                        "거래처명": cp, "차변": D.values, "대변": C.values, "잔액": bal})

    # FR-13 메타필드: 열이 있으면 보존, 없으면 결측(뒤에서 전부 결측이면 출력 제외)
    def _col(key):
        j = cm.get(key)
        return tx.iloc[:, j] if j is not None else None
    def _text(col):
        """문자열로 정리하되 결측·공백은 NaN으로 유지한다.
           astype(str)만 쓰면 결측이 'nan' 문자열이 되어, 뒤의 notna() 기반
           '메타필드 존재' 판정과 fraud score의 만점(MAXPOSS)이 왜곡된다."""
        v = col.astype(str).str.strip()
        blank = col.isna() | (v == "") | v.str.lower().isin(["nan", "none", "nat"])
        return v.mask(blank, np.nan)

    a, ind, jt = _col("author"), _col("inputdate"), _col("jtype")
    std["작성자"] = _text(a).values if a is not None else np.nan
    std["입력일"] = parse_dates(ind, year).values if ind is not None else pd.NaT
    std["전표유형"] = _text(jt).values if jt is not None else np.nan

    # 기초(이월) — 시트별형에서만 의미
    openD = openC = 0.0
    if cm["memo"] is not None:
        nonx = data[~mask]
        mn = nonx.iloc[:, cm["memo"]].map(norm)
        op = nonx[mn.str.contains("이월", na=False)]
        if len(op):
            openD = float(_to_num(op.iloc[:, cm["debit"]]).fillna(0).iloc[0])
            openC = float(_to_num(op.iloc[:, cm["credit"]]).fillna(0).iloc[0])
    return std, (openD, openC)


def load_ledger(path):
    """파일 하나 → dict(gl, tb, meta). 실패 시 예외."""
    path = Path(path)
    year = infer_year(path.name)
    xl = pd.ExcelFile(path)                            # 엔진 자동(.xls=xlrd)

    parsed = []
    for s in xl.sheet_names:
        raw = xl.parse(s, header=None)
        hr = find_header_row(raw)
        if hr is None:
            continue
        cols = [norm(v) for v in raw.iloc[hr].tolist()]
        cm = build_colmap(cols)
        if cm["debit"] is None or cm["credit"] is None or not cm["date_cands"]:
            continue
        # 날짜 열 확정: 후보 중 파싱 성공률 최고
        best_c, best_r = None, -1
        body = raw.iloc[hr + 1: hr + 60]
        for c in cm["date_cands"]:
            r = parse_dates(body.iloc[:, c], year).notna().mean() if len(body) else 0
            if r > best_r:
                best_c, best_r = c, r
        cm["date"] = best_c
        parsed.append(dict(sheet=s, raw=raw, hr=hr, cm=cm))

    if not parsed:
        raise ValueError("차변/대변 헤더를 가진 데이터 시트를 찾지 못함")

    # 단일표형 판별: 계정 식별 열(코드 우선, 없으면 계정명)의 고유값이 많은 시트(가장 큰 것)
    flats = []
    for p in parsed:
        idcol = p["cm"]["acctcode"] if p["cm"]["acctcode"] is not None else p["cm"]["acctname"]
        if idcol is not None:
            data = p["raw"].iloc[p["hr"] + 1:]
            nd = data.iloc[:, idcol].nunique(dropna=True)
            if nd > 5:
                flats.append((len(data), p))
    frames, tb_rows = [], []
    if flats:
        # 같은 구조(헤더 구성이 동일)의 시트끼리 묶는다. 원장이 여러 시트로 나뉜 경우를
        # 모두 적재하되, 구조가 다른 시트(요약·피벗 등)가 섞여 중복 집계되는 것은 막는다.
        groups = {}
        for size, p in flats:
            hdr = [norm(v) for v in p["raw"].iloc[p["hr"]].tolist()]
            sig = tuple(h for h in hdr if h and h.lower() != "nan")
            groups.setdefault(sig, []).append((size, p))
        # 총 행수가 가장 많은 구조를 본문 원장으로 채택(단일 시트면 기존 동작과 동일)
        best_sig = max(groups, key=lambda k: sum(s for s, _ in groups[k]))
        for _, p in groups[best_sig]:
            std, _ = _std_from_sheet(p["sheet"], p["raw"], p["hr"], p["cm"], year,
                                     use_acct_cols=True)
            if std is not None and not std.empty:
                frames.append(std)
        layout = "단일표형"
    else:
        layout = "시트별형"
        for p in parsed:
            std, (oD, oC) = _std_from_sheet(p["sheet"], p["raw"], p["hr"], p["cm"], year, use_acct_cols=True)
            if std is None or std.empty:
                continue
            code = str(std["계정코드"].iloc[0]).strip()
            if code in ("None", "nan", ""):     # 계정 식별 실패(요약/커버 시트) → 제외
                continue
            frames.append(std)
            tb_rows.append(dict(계정코드=code, 계정명=std["계정명"].iloc[0],
                                기초차변=oD, 기초대변=oC, 거래건수=len(std)))

    if not frames:
        raise ValueError(
            "인식 가능한 계정·거래를 찾지 못했습니다. "
            "계정별원장(계정마다 시트가 있거나, 한 표에 계정코드/계정명·차변·대변 열이 있는 형식)인지 확인하세요. "
            "분개장 등 다른 형식은 지원하지 않습니다.")
    gl = pd.concat(frames, ignore_index=True)
    gl["계정코드"] = gl["계정코드"].astype(str).str.strip()
    # 계정코드가 없거나 비숫자(계정명을 코드로 쓴 경우) → 계정명 기준 합성 숫자코드 부여
    code_map = None
    if not gl["계정코드"].str.match(r"^\d+$").all():
        code_map = {n: f"9{i + 1:05d}" for i, n in enumerate(gl["계정명"].astype(str).unique())}
        gl["계정코드"] = gl["계정명"].astype(str).map(code_map)
    gl["전표일자"] = pd.to_datetime(gl["전표일자"])
    gl = gl.dropna(subset=["전표일자"]).sort_values("전표일자").reset_index(drop=True)
    gl["전표월"] = gl["전표일자"].dt.to_period("M").astype(str)

    if layout == "단일표형":                            # 단일표는 계정별로 tb 집계
        g = gl.groupby(["계정코드", "계정명"])
        tb = g.agg(거래건수=("차변", "size")).reset_index()
        tb["기초차변"] = 0.0; tb["기초대변"] = 0.0
        tb["시스템누계차변"] = np.nan; tb["시스템누계대변"] = np.nan
    else:
        tb = pd.DataFrame(tb_rows)
        # GL에 합성 계정코드를 부여했다면 TB에도 '계정명 기준'으로 똑같이 적용한다.
        # (적용하지 않으면 TB는 원래 코드(계정명)를 들고 있어
        #  fr02_validate.py의 tb.merge(det, on="계정코드") 역산 대사가 통째로 실패한다.)
        if code_map is not None and not tb.empty:
            tb["계정코드"] = (tb["계정명"].astype(str).map(code_map)
                            .fillna(tb["계정코드"].astype(str)))
        tb["시스템누계차변"] = np.nan; tb["시스템누계대변"] = np.nan

    company = _company_name(path, parsed)
    # FR-13 메타필드: 실제 값이 있는 것만 표준 원장에 포함(적응형)
    out_cols = ["계정코드", "계정명", "전표일자", "전표번호", "적요", "거래처명",
                "차변", "대변", "잔액", "전표월"]
    meta_present = [c for c in ["작성자", "입력일", "전표유형"]
                    if c in gl.columns and gl[c].notna().any()]
    out_cols += meta_present
    meta = dict(company=company, layout=layout, year=year,
                n_accounts=gl["계정코드"].nunique(), n_rows=len(gl),
                debit=float(gl["차변"].sum()), credit=float(gl["대변"].sum()),
                meta_fields=meta_present)
    return dict(gl=gl[out_cols], tb=tb, meta=meta)


def _company_name(path, parsed):
    for p in parsed[:1]:
        for i in range(min(6, len(p["raw"]))):
            for cell in p["raw"].iloc[i].tolist():
                m = re.search(r"회\s*사\s*(?:명)?\s*:\s*(.+)", str(cell))
                if m:
                    v = re.sub(r"\[?\d+\]?\.?\s*", "", m.group(1)).strip()
                    if v:
                        return v[:20]
    base = path.stem
    for t in ["계정별원장", "총계정원장", "계정과목원장", "계정원장", "원장", "분개장",
              "세목", "세부정보", "세부", "최종본", "최종", "수정본", "수정", "사본",
              "FY2025", "FY", "년", "분기", "및", "Q", "PBC"]:
        base = base.replace(t, "")
    base = re.sub(r"\d", "", base)
    base = re.sub(r"[._\-()\s]+", " ", base).strip()
    return base if len(base) >= 2 else path.stem   # 잔여물만 남으면 원본 파일명 사용


if __name__ == "__main__":
    import glob
    import os
    BASE = Path(__file__).resolve().parent.parent
    files = [f for f in glob.glob(str(BASE / "data" / "*.xls*")) if "분개장" not in f]
    print(f"{'파일':40s} {'회사':12s} {'구조':8s} {'계정':>5s} {'행수':>8s}  대차일치")
    print("-" * 92)
    for f in sorted(files):
        name = os.path.basename(f)
        if os.path.getsize(f) > 100 * 1e6:
            print(f"{name[:38]:40s} (건너뜀: {os.path.getsize(f)/1e6:.0f}MB 대용량 — 이 PC 메모리 초과 위험)")
            continue
        try:
            r = load_ledger(f)
            m = r["meta"]
            ok = abs(m["debit"] - m["credit"]) < 1
            print(f"{name[:38]:40s} {m['company'][:11]:12s} {m['layout']:8s} "
                  f"{m['n_accounts']:5d} {m['n_rows']:8,d}  {'✅' if ok else '❌ 차이='+format(m['debit']-m['credit'],',.0f')}")
        except Exception as e:
            print(f"{name[:38]:40s} !! 실패: {type(e).__name__}: {str(e)[:45]}")
