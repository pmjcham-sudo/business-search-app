import streamlit as st
import requests
import pandas as pd
from math import radians, sin, cos, sqrt, atan2
from datetime import date

# =========================
# 카카오 REST API 키
# =========================
KAKAO_API_KEY = st.secrets["KAKAO_API_KEY"]

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
def search_kakao(keyword, center_lat, center_lon, radius, page=1):
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
        "sort": "distance"
    }

    response = requests.get(url, headers=headers, params=params)

    if response.status_code != 200:
        st.error("카카오 API 요청 실패")
        st.write(response.text)
        return {"documents": []}

    return response.json()


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


# =========================
# 데이터 수집 함수
# =========================
def collect_places(center_name, center_lat, center_lon, keywords, radius, max_page):
    rows = []

    for keyword in keywords:
        keyword = keyword.strip()

        if keyword == "":
            continue

        for page in range(1, max_page + 1):
            data = search_kakao(
                keyword=keyword,
                center_lat=center_lat,
                center_lon=center_lon,
                radius=radius,
                page=page
            )

            documents = data.get("documents", [])

            if len(documents) == 0:
                continue

            for d in documents:
                try:
                    lat = float(d["y"])
                    lon = float(d["x"])

                    road_address = d.get("road_address_name", "")
                    jibun_address = d.get("address_name", "")
                    final_address = road_address if road_address else jibun_address

                    rows.append({
                        "기준장소": center_name,
                        "검색키워드": keyword,
                        "업체명": d.get("place_name", ""),
                        "카테고리": d.get("category_name", ""),
                        "도로명주소": road_address,
                        "지번주소": jibun_address,
                        "건물주소": make_building_address(final_address),
                        "전화번호": d.get("phone", ""),
                        "위도": lat,
                        "경도": lon,
                        "기준장소거리_m": haversine(
                            center_lat,
                            center_lon,
                            lat,
                            lon
                        ),
                        "카카오URL": d.get("place_url", ""),
                        "전문인력수": "",
                        "추정임직원수": "",
                        "출처URL": d.get("place_url", ""),
                        "최종확인일": str(date.today()),
                        "메모": ""
                    })

                except Exception as e:
                    st.warning(f"개별 데이터 처리 오류: {e}")

    df = pd.DataFrame(rows)

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
            "전문인력수",
            "추정임직원수",
            "출처URL",
            "최종확인일",
            "메모"
        ]
    ]

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
    max_value=20000,
    value=1000,
    step=100
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
            result_df = collect_places(
                center_name=center_name,
                center_lat=center_lat,
                center_lon=center_lon,
                keywords=keywords,
                radius=radius,
                max_page=max_page
            )

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

            st.dataframe(result_df, use_container_width=True)

            # CSV 다운로드
            csv_data = result_df.to_csv(index=False, encoding="utf-8-sig")

            st.download_button(
                label="CSV 다운로드",
                data=csv_data,
                file_name="nearby_business_search_result.csv",
                mime="text/csv"
            )
