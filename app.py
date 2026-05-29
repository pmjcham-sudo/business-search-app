import streamlit as st
import requests
import pandas as pd
from math import radians, sin, cos, sqrt, atan2
from datetime import date
import urllib.parse

# =========================
# 카카오 REST API 키
# =========================
KAKAO_API_KEY = st.secrets["KAKAO_API_KEY"]
DATA_GO_KR_API_KEY = st.secrets.get("DATA_GO_KR_API_KEY", "")

# =========================
# 거리 계산 함수
# =========================
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1))
        * cos(radians(lat2))
        * sin(dlon / 2) ** 2
    )

    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return round(R * c)


# =========================
# 카카오 장소 검색 함수
# =========================
def search_kakao(keyword, center_lat, center_lon, radius, page=1, sort_type="distance"):
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"

    headers = {
        "Authorization": f"KakaoAK {KAKAO_API_KEY}"
    }

    params = {
        "query": keyword,
        "x": center_lon,
        "y": center_lat,
        "radius": radius,
        "page": page,
        "size": 15,
        "sort": sort_type
    }

    response = requests.get(url, headers=headers, params=params)

    if response.status_code != 200:
        st.error("카카오 API 요청 실패")
        st.write(response.text)
        return {"documents": []}

    return response.json()
def normalize_company_name(text):
    text = str(text)

    remove_words = [
        "주식회사", "(주)", "㈜",
        "법무법인", "세무법인", "회계법인", "노무법인",
        "법률사무소", "세무사", "변호사", "회계사",
        " ", "-", "_", ".", ",", "·", "(", ")", "[", "]"
    ]

    for word in remove_words:
        text = text.replace(word, "")

    return text.lower()


def address_front(address):
    address = str(address)
    parts = address.split()

    if len(parts) >= 4:
        return " ".join(parts[:4])
    elif len(parts) >= 3:
        return " ".join(parts[:3])
    else:
        return address


def search_nps_workplace(place_name):
    """
    국민연금 가입사업장 API에서 사업장명으로 검색.
    API 엔드포인트/필드명은 공공데이터포털 활용명세와 다를 수 있어서
    response 구조를 최대한 유연하게 처리함.
    """

    if not DATA_GO_KR_API_KEY:
        return []

    # 공공데이터포털 활용명세에서 제공하는 endpoint가 다를 수 있음.
    # 아래 URL은 적용 후 오류가 나면 data.go.kr의 '미리보기/활용명세' endpoint로 교체해야 함.
    url = "https://apis.data.go.kr/B552015/NpsBplcInfoInqireService/getBassInfoSearch"

    params = {
        "serviceKey": DATA_GO_KR_API_KEY,
        "wkpl_nm": place_name,
        "numOfRows": 10,
        "pageNo": 1,
        "resultType": "json"
    }

    try:
        response = requests.get(url, params=params, timeout=8)

        if response.status_code != 200:
            return []

        data = response.json()

        body = data.get("response", {}).get("body", {})
        items = body.get("items", {})

        if isinstance(items, dict):
            item = items.get("item", [])
        else:
            item = items

        if isinstance(item, dict):
            return [item]

        if isinstance(item, list):
            return item

        return []

    except Exception:
        return []

def get_value_from_item(item, candidates):
    for key in candidates:
        if key in item and item.get(key) not in [None, ""]:
            return item.get(key)
    return ""


def match_nps_employee_count(place_name, road_address, jibun_address):
    items = search_nps_workplace(place_name)

    if len(items) == 0:
        return {
            "추정임직원수": "",
            "임직원수출처": "",
            "임직원수기준": "",
            "임직원수신뢰도": "미확인",
            "국민연금매칭사업장명": "",
            "국민연금매칭주소": ""
        }

    kakao_name_norm = normalize_company_name(place_name)
    kakao_addr = road_address if str(road_address) != "" else jibun_address
    kakao_addr_front = address_front(kakao_addr)

    best_match = None
    best_score = 0

    for item in items:
        # 공공데이터 필드명이 명세에 따라 다를 수 있어서 후보명을 여러 개 둠
        nps_name = get_value_from_item(
            item,
            ["wkplNm", "wkpl_nm", "사업장명", "bzowrNm"]
        )

        nps_addr = get_value_from_item(
            item,
            ["wkplRoadNmDtlAddr", "wkplRnDtlAddr", "wkplAddr", "주소", "wkpl도로명상세주소"]
        )

        nps_count = get_value_from_item(
            item,
            ["jnngpCnt", "가입자수", "crrmmNtcAmt", "wkplJnngpCnt"]
        )

        nps_name_norm = normalize_company_name(nps_name)
        nps_addr_front = address_front(nps_addr)

        score = 0

        if kakao_name_norm and nps_name_norm:
            if kakao_name_norm == nps_name_norm:
                score += 70
            elif kakao_name_norm in nps_name_norm or nps_name_norm in kakao_name_norm:
                score += 50

        if kakao_addr_front and nps_addr_front:
            if kakao_addr_front == nps_addr_front:
                score += 40
            elif kakao_addr_front.split()[0:3] == nps_addr_front.split()[0:3]:
                score += 25

        if score > best_score:
            best_score = score
            best_match = {
                "name": nps_name,
                "addr": nps_addr,
                "count": nps_count
            }

    if best_match is None or best_score < 50:
        return {
            "추정임직원수": "",
            "임직원수출처": "국민연금 가입사업장 내역",
            "임직원수기준": "사업장가입자 수",
            "임직원수신뢰도": "수동확인필요",
            "국민연금매칭사업장명": "",
            "국민연금매칭주소": ""
        }

    if best_score >= 90:
        confidence = "상"
    elif best_score >= 70:
        confidence = "중"
    else:
        confidence = "하"

    return {
        "추정임직원수": best_match["count"],
        "임직원수출처": "국민연금 가입사업장 내역",
        "임직원수기준": "사업장가입자 수",
        "임직원수신뢰도": confidence,
        "국민연금매칭사업장명": best_match["name"],
        "국민연금매칭주소": best_match["addr"]
    }

# =========================
# 건물주소 간단 추출
# =========================
def make_building_address(address):
    if not address:
        return ""

    parts = address.split()

    if len(parts) >= 4:
        return " ".join(parts[:4])
    else:
        return address
def is_valid_result(keyword, place_name, category_name):
    keyword = str(keyword)
    place_name = str(place_name)
    category_name = str(category_name)

    text = place_name + " " + category_name

    tax_keywords = [
        "세무", "세무사", "세무법인",
        "회계", "회계사", "회계법인"
    ]

    law_keywords = [
        "법무법인", "변호사", "법률", "로펌", "법률사무소"
    ]

    scrivener_keywords = [
        "법무사"
    ]

    hospital_keywords = [
        "병원", "의원", "치과", "한의원", "약국",
        "내과", "정형외과", "피부과", "이비인후과",
        "안과", "산부인과", "소아과", "정신건강의학과"
    ]

    exclude_keywords = [
        "학원", "어학원", "교습소",
        "부동산", "공인중개사",
        "카페", "식당", "음식점",
        "미용실", "네일", "피부관리",
        "행정사"
    ]

    # 제외어 우선 적용
    if any(bad in text for bad in exclude_keywords):
        # 사용자가 행정사를 검색한 경우에는 행정사 결과를 살림
        if "행정사" not in keyword:
            return False

    # 세무/회계 계열 검색
    if "세무" in keyword or "회계" in keyword:
        return any(word in text for word in tax_keywords)

    # 법무법인/변호사/로펌 계열 검색
    if "법무법인" in keyword or "변호사" in keyword or "로펌" in keyword or "법률" in keyword:
        return any(word in text for word in law_keywords)

    # 법무사 검색
    if "법무사" in keyword:
        return any(word in text for word in scrivener_keywords)

    # 병의원/의료 계열 검색
    if any(word in keyword for word in hospital_keywords):
        return any(word in text for word in hospital_keywords)

    # 그 외 일반 검색어는 일단 통과
    return True

# =========================
# 데이터 수집 함수
# =========================
def collect_places(center_name, center_lat, center_lon, keywords, radius, max_page):
    rows = []

    for keyword in keywords:
        keyword = keyword.strip()

        if keyword == "":
            continue

        for sort_type in ["distance", "accuracy"]:
            for page in range(1, max_page + 1):
                data = search_kakao(
                    keyword=keyword,
                    center_lat=center_lat,
                    center_lon=center_lon,
                    radius=radius,
                    page=page,
                    sort_type=sort_type
                )

                documents = data.get("documents", [])

                if len(documents) == 0:
                    continue

                for d in documents:
                    try:
                        lat = float(d["y"])
                        lon = float(d["x"])

                        place_name = d.get("place_name", "")
                        category_name = d.get("category_name", "")
                        
                        if not is_valid_result(keyword, place_name, category_name):
                            continue

                        distance_m = haversine(
                            center_lat,
                            center_lon,
                            lat,
                            lon
                        )
                        

                        # 실제 반경 기준으로 다시 필터링
                        if distance_m > radius:
                            continue

                        road_address = d.get("road_address_name", "")
                        jibun_address = d.get("address_name", "")
                        final_address = road_address if road_address else jibun_address
                        

                        rows.append({
                            "기준장소": center_name,
                            "검색키워드": keyword,
                            "검색방식": "빠른검색",
                            "정렬방식": sort_type,
                            "업체명": place_name,
                            "카테고리": category_name,
                            "도로명주소": road_address,
                            "지번주소": jibun_address,
                            "건물주소": make_building_address(final_address),
                            "전화번호": d.get("phone", ""),
                            "위도": lat,
                            "경도": lon,
                            "기준장소거리_m": distance_m,
                            "카카오URL": d.get("place_url", ""),
                            "전문인력수": "",
                            "추정임직원수": "",
                            "임직원수출처": "",
                            "임직원수기준": "",
                            "임직원수신뢰도": "",
                            "국민연금매칭사업장명": "",
                            "국민연금매칭주소": "",
                            "출처URL": d.get("place_url", ""),
                            "최종확인일": str(date.today()),
                            "메모": ""
                        })

                    except Exception as e:
                        st.warning(f"개별 데이터 처리 오류: {e}")

    return make_result_dataframe(rows, radius)
    def generate_grid_points(center_lat, center_lon, radius_m, step_m):
        points = []

        # 대략적인 위도/경도 변환
        lat_per_meter = 1 / 111000
        lon_per_meter = 1 / (111000 * cos(radians(center_lat)))

        steps = int(radius_m // step_m) + 1

        for i in range(-steps, steps + 1):
            for j in range(-steps, steps + 1):
                new_lat = center_lat + (i * step_m * lat_per_meter)
                new_lon = center_lon + (j * step_m * lon_per_meter)

                distance_from_center = haversine(
                    center_lat,
                    center_lon,
                    new_lat,
                    new_lon
                )

                if distance_from_center <= radius_m:
                    points.append((new_lat, new_lon))

        return points


def collect_places_grid(center_name, center_lat, center_lon, keywords, radius, max_page, grid_step):
    rows = []

    grid_points = generate_grid_points(
        center_lat=center_lat,
        center_lon=center_lon,
        radius_m=radius,
        step_m=grid_step
    )

    st.write(f"정밀 검색 격자점 수: {len(grid_points)}개")

    for keyword in keywords:
        keyword = keyword.strip()

        if keyword == "":
            continue

        for idx, point in enumerate(grid_points):
            grid_lat, grid_lon = point

            for sort_type in ["distance", "accuracy"]:
                for page in range(1, max_page + 1):
                    data = search_kakao(
                        keyword=keyword,
                        center_lat=grid_lat,
                        center_lon=grid_lon,
                        radius=grid_step,
                        page=page,
                        sort_type=sort_type
                    )

                    documents = data.get("documents", [])

                    if len(documents) == 0:
                        continue

                    for d in documents:
                        try:                            
                            lat = float(d["y"])
                            lon = float(d["x"])

                            place_name = d.get("place_name", "")
                            category_name = d.get("category_name", "")

                            if not is_valid_result(keyword, place_name, category_name):
                                continue
                            # 최종 거리는 원래 기준장소 기준으로 계산
                            distance_m = haversine(
                                center_lat,
                                center_lon,
                                lat,
                                lon
                            )

                            # 최종적으로 원래 검색 반경 밖이면 제외
                            if distance_m > radius:
                                continue

                            road_address = d.get("road_address_name", "")
                            jibun_address = d.get("address_name", "")
                            final_address = road_address if road_address else jibun_address

                            nps_result = match_nps_employee_count(
                                place_name,
                                road_address,
                                jibun_address
                            )

                            rows.append({
                                "기준장소": center_name,
                                "검색키워드": keyword,
                                "검색방식": "정밀검색",
                                "정렬방식": sort_type,
                                "업체명": place_name,
                                "카테고리": category_name,
                                "도로명주소": road_address,
                                "지번주소": jibun_address,
                                "건물주소": make_building_address(final_address),
                                "전화번호": d.get("phone", ""),
                                "위도": lat,
                                "경도": lon,
                                "기준장소거리_m": distance_m,
                                "카카오URL": d.get("place_url", ""),
                                "전문인력수": "",
                                "추정임직원수": nps_result["추정임직원수"],
                                "임직원수출처": nps_result["임직원수출처"],
                                "임직원수기준": nps_result["임직원수기준"],
                                "임직원수신뢰도": nps_result["임직원수신뢰도"],
                                "국민연금매칭사업장명": nps_result["국민연금매칭사업장명"],
                                "국민연금매칭주소": nps_result["국민연금매칭주소"],
                                "출처URL": d.get("place_url", ""),
                                "최종확인일": str(date.today()),
                                "메모": ""
                            })

                        except Exception as e:
                            st.warning(f"개별 데이터 처리 오류: {e}")

    return make_result_dataframe(rows, radius)


def make_result_dataframe(rows, radius):
    df = pd.DataFrame(rows)
    
    # 네이버지도 검색 URL 추가
    df["네이버지도검색URL"] = df["업체명"].apply(
        lambda x: "https://map.naver.com/p/search/" + urllib.parse.quote(str(x))
    )
    
    # 검증 상태 기본값 추가
    df["검증상태"] = "미확인"
    
    if len(df) == 0:
        return df

    # 중복 제거
    df = df.drop_duplicates(subset=["업체명", "도로명주소"])

    # 반경 재필터링
    df = df[df["기준장소거리_m"] <= radius]

    if len(df) == 0:
        return df

    # 거리순 정렬
    df = df.sort_values("기준장소거리_m")

    # 같은 건물 업체 수
    df["같은건물업체수"] = df.groupby("건물주소")["업체명"].transform("count")

    # 컬럼 순서 정리
    df = df[
        [
            "업체명",
            "검색키워드",
            "검색방식",
            "정렬방식",
            "카테고리",
            "기준장소",
            "도로명주소",
            "지번주소",
            "건물주소",
            "같은건물업체수",
            "전화번호",
            "기준장소거리_m",
            "위도",
            "경도",
            "카카오URL",
            "네이버지도검색URL",
            "검증상태",
            "전문인력수",
            "추정임직원수",
            "출처URL",
            "최종확인일",
            "메모"
        ]
    ]

    return df

def add_nps_info_to_dataframe(df):
    if len(df) == 0:
        return df

    # 인덱스 초기화: 진행률 오류 방지
    df = df.reset_index(drop=True)

    # 같은 업체명+주소 조합은 한 번만 조회하기 위한 캐시
    nps_cache = {}

    progress = st.progress(0)
    total = len(df)

    for position, row in df.iterrows():
        place_name = row.get("업체명", "")
        road_address = row.get("도로명주소", "")
        jibun_address = row.get("지번주소", "")

        cache_key = str(place_name) + "|" + str(road_address)

        if cache_key in nps_cache:
            nps_result = nps_cache[cache_key]
        else:
            nps_result = match_nps_employee_count(
                place_name,
                road_address,
                jibun_address
            )
            nps_cache[cache_key] = nps_result

        df.at[position, "추정임직원수"] = nps_result["추정임직원수"]
        df.at[position, "임직원수출처"] = nps_result["임직원수출처"]
        df.at[position, "임직원수기준"] = nps_result["임직원수기준"]
        df.at[position, "임직원수신뢰도"] = nps_result["임직원수신뢰도"]
        df.at[position, "국민연금매칭사업장명"] = nps_result["국민연금매칭사업장명"]
        df.at[position, "국민연금매칭주소"] = nps_result["국민연금매칭주소"]

        # 진행률은 반드시 0~1 사이로 제한
        progress_value = (position + 1) / total
        progress.progress(min(progress_value, 1.0))

    progress.empty()

    return df

# =========================
# Streamlit 화면
# =========================
st.set_page_config(
    page_title="주변 사업장 검색 도구",
    layout="wide"
)

st.title("주변 사업장 검색 도구")
st.caption("기준 장소와 검색 키워드를 바꿔가며 주변 사업장을 수집하고 CSV로 저장할 수 있습니다.")

st.divider()

# =========================
# 사이드바 입력
# =========================
st.sidebar.header("검색 조건")

preset = st.sidebar.selectbox(
    "기준 장소 프리셋",
    [
        "한국투자증권 광화문센터",
        "광화문역",
        "종각역",
        "직접 입력"
    ]
)

if preset == "한국투자증권 광화문센터":
    center_name = "한국투자증권 광화문센터"
    default_lat = 37.5705
    default_lon = 126.9780

elif preset == "광화문역":
    center_name = "광화문역"
    default_lat = 37.571607
    default_lon = 126.976944

elif preset == "종각역":
    center_name = "종각역"
    default_lat = 37.5702
    default_lon = 126.9820

else:
    center_name = st.sidebar.text_input("기준 장소명", "내 기준 장소")
    default_lat = 37.5705
    default_lon = 126.9780

center_lat = st.sidebar.number_input(
    "기준 위도",
    value=default_lat,
    format="%.6f"
)

center_lon = st.sidebar.number_input(
    "기준 경도",
    value=default_lon,
    format="%.6f"
)

radius = st.sidebar.slider(
    "검색 반경(m)",
    min_value=100,
    max_value=5000,
    value=1000,
    step=100,
    help="빠른 검색은 가까운 결과 위주로 가져옵니다. 1km 이상은 정밀 검색 사용을 권장합니다."
)

search_mode = st.sidebar.radio(
    "검색 방식",
    ["빠른 검색", "정밀 검색"],
    help="빠른 검색은 기준점 1곳에서 검색합니다. 정밀 검색은 반경 안을 여러 구역으로 나누어 더 많이 수집합니다."
)

use_nps = st.sidebar.checkbox(
    "국민연금 가입자 수 조회",
    value=False,
    help="켜면 추정임직원수를 조회합니다. 검색 시간이 오래 걸릴 수 있습니다."
)

grid_step = st.sidebar.selectbox(
    "정밀 검색 간격",
    [300, 500, 700, 1000],
    index=1,
    help="정밀 검색에서 격자점을 몇 m 간격으로 만들지 정합니다. 숫자가 작을수록 더 촘촘하지만 느려집니다."
)

max_page = st.sidebar.slider(
    "검색 페이지 수",
    min_value=1,
    max_value=3,
    value=3,
    step=1
)

keyword_text = st.sidebar.text_area(
    "검색 키워드",
    value="법무법인\n세무법인\n변호사\n세무사",
    height=180
)

keywords = keyword_text.split("\n")

search_button = st.sidebar.button("검색 실행")

# =========================
# 본문 안내
# =========================
st.subheader("사용 방법")

st.write(
    """
    1. 왼쪽에서 기준 장소를 선택하거나 직접 위도·경도를 입력합니다.  
    2. 검색 키워드에 원하는 업종을 줄바꿈으로 입력합니다.  
    3. 검색 실행을 누르면 주변 사업장 목록이 표로 생성됩니다.  
    4. 결과는 CSV로 다운로드할 수 있습니다.
    """
)

st.info("예시 키워드: 법무법인, 세무법인, 병의원, 치과, 한의원, 약국, 회계법인, 노무법인, 부동산중개업소")

# =========================
# 검색 실행
# =========================
if search_button:
    if KAKAO_API_KEY == "여기에_네_REST_API_KEY":
        st.error("코드 상단의 KAKAO_API_KEY에 실제 카카오 REST API 키를 넣어야 합니다.")

    else:
        with st.spinner("검색 중입니다..."):
            if search_mode == "빠른 검색":
                result_df = collect_places(
                    center_name=center_name,
                    center_lat=center_lat,
                    center_lon=center_lon,
                    keywords=keywords,
                    radius=radius,
                    max_page=max_page
                )
            else:
                result_df = collect_places_grid(
                    center_name=center_name,
                    center_lat=center_lat,
                    center_lon=center_lon,
                    keywords=keywords,
                    radius=radius,
                    max_page=max_page,
                    grid_step=grid_step
                )
            if use_nps and len(result_df) > 0:
                with st.spinner("국민연금 가입자 수를 조회하는 중입니다..."):
                    result_df = add_nps_info_to_dataframe(result_df)
        
        st.divider()

        if len(result_df) == 0:
            st.warning("검색 결과가 없습니다. 키워드나 반경을 바꿔보세요.")

        else:
            st.success(f"총 {len(result_df)}개 업체를 찾았습니다.")

            # 요약 지표
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("검색 결과 수", len(result_df))

            with col2:
                st.metric("가장 가까운 거리", f"{result_df['기준장소거리_m'].min()} m")

            with col3:
                st.metric("검색 반경", f"{radius} m")

            # 키워드별 요약
            st.subheader("키워드별 결과 수")

            summary_keyword = (
                result_df.groupby("검색키워드")
                .agg(업체수=("업체명", "count"))
                .reset_index()
                .sort_values("업체수", ascending=False)
            )

            st.dataframe(summary_keyword, use_container_width=True)

            # 건물별 요약
            st.subheader("건물별 요약")

            building_summary = (
                result_df.groupby("건물주소")
                .agg(
                    업체수=("업체명", "count"),
                    가장가까운거리_m=("기준장소거리_m", "min")
                )
                .reset_index()
                .sort_values("가장가까운거리_m")
            )

            st.dataframe(building_summary, use_container_width=True)

            # 전체 결과
            st.subheader("전체 검색 결과")

            st.dataframe(
                result_df,
                use_container_width=True,
                column_config={
                    "카카오URL": st.column_config.LinkColumn(
                        "카카오지도",
                        display_text="열기"
                    ),
                    "네이버지도검색URL": st.column_config.LinkColumn(
                        "네이버지도",
                        display_text="열기"
                    ),
                    "출처URL": st.column_config.LinkColumn(
                        "출처",
                        display_text="열기"
                    )
                }
            )

            # CSV 다운로드
            csv_data = result_df.to_csv(index=False, encoding="utf-8-sig")

            st.download_button(
                label="CSV 다운로드",
                data=csv_data,
                file_name="nearby_business_search_result.csv",
                mime="text/csv"
            )
