"""제휴 판매처 목록과 제휴 링크 생성 — 링크프라이스(LP) 딥링크 + 트래블페이아웃(TP) 즉시 링크.

네이버 redirect 체인(tivan/nlabel)은 네이버 제휴 추적이라 우리 수익이 없다(실측 2026-10-19).
LP 딥링크(l=9999&tu=)로 OTA 검색 URL을 감싸면:
  - 우리 제휴 ID(A100700961)가 쿠키에 박힌다 (OUID=A100700961 확인)
  - 만료 없음 (네이버 redirect 는 수십 초)

URL 포맷 (2026-10-19 실측):
  트립닷컴  kr.trip.com/flights/showfarefirst?dcity=SEL(도시코드)…
  마이리얼트립 flights.myrealtrip.com/international?dep=ICN…
  NOL      air.nol.kr/international?dep=ICN…
  아고다     agoda.com/ko-kr/flights (검색 파라미터 미지원)
  Kiwi(TP)  kiwi.com/en/search/results/{도시-나라}/{도시-나라}/{날짜}/{날짜}/
            ⚠️ 구 /en/search/ICN/NRT/ 포맷은 2026-10-19부로 404 (실측)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Literal, Optional
from urllib.parse import quote

# ── 계정 ────────────────────────────────────────────────────────────
LP_AFFILIATE_ID = "A100700961"          # 링크프라이스 제휴 ID
TP_MARKER = "703382"                     # 트래블페이아웃 마커
TP_TRS = "585871"                        # 트래블페이아웃 trs
TP_KIWI_P = "4136"                       # Kiwi 브랜드 p 값
TP_SUB_ID = "rockpin"                    # 하위 채널 구분


def _d(d: date) -> str:
    return f"{d:%Y-%m-%d}"


# ── Trip.com 도시코드 (다공항 도시는 광역 코드 사용, 실측 SEL/TYO/SHA OK) ──
TRIP_CITY = {
    "ICN": "SEL", "GMP": "SEL", "SSN": "SEL",     # 서울
    "NRT": "TYO", "HND": "TYO",                    # 도쿄
    "KIX": "OSA", "ITM": "OSA", "UKB": "OSA",      # 오사카
    "PVG": "SHA", "SHA": "SHA",                    # 상하이
    "PEK": "BJS", "PKX": "BJS",                    # 베이징
}


def _trip(code: str) -> str:
    return TRIP_CITY.get(code, code)


# ── Kiwi 슬러그 (2026-10-19 실측: guam-united-states ✓, hong-kong ✓, …) ──
# 미등록 공항 → None → Kiwi 홈 링크(제휴쿠키는 설정됨)
KIWI_SLUG = {
    # 한국 출발
    "ICN": "seoul-south-korea", "GMP": "seoul-south-korea", "SEL": "seoul-south-korea",
    "PUS": "busan-south-korea", "CJU": "jeju-city-south-korea", "TAE": "daegu-south-korea",
    "CJJ": "cheongju-south-korea", "KWJ": "gwangju-south-korea", "USN": "ulsan-south-korea",
    "RSU": "yeosu-south-korea", "KUV": "gunsan-south-korea", "MWX": "muan-south-korea",
    "WJU": "wonju-south-korea", "HIN": "jinju-south-korea",
    # 일본
    "NRT": "tokyo-japan", "HND": "tokyo-japan", "KIX": "osaka-japan", "ITM": "osaka-japan",
    "UKB": "osaka-japan", "FUK": "fukuoka-japan", "CTS": "sapporo-japan",
    "NGO": "nagoya-japan", "OKA": "okinawa-island-japan", "KMJ": "kumamoto-japan",
    "MYJ": "matsuyama-japan", "KOJ": "kagoshima-japan", "HIJ": "hiroshima-japan",
    "KKJ": "kitakyushu-japan", "TAK": "takamatsu-japan", "FSZ": "shizuoka-japan",
    "HKD": "hakodate-japan", "YGJ": "yonago-japan", "OIT": "oita-japan",
    "AOJ": "aomori-japan", "ISG": "ishigaki-japan", "SDJ": "sendai-japan",
    "MMB": "memanbetsu-japan", "AKJ": "asahikawa-japan", "KMQ": "komatsu-japan",
    # 중국
    "PVG": "shanghai-china", "SHA": "shanghai-china", "PEK": "beijing-china",
    "PKX": "beijing-china", "TAO": "qingdao-china", "YNT": "yantai-china",
    "DLC": "dalian-china", "CAN": "guangzhou-china", "SHE": "shenyang-china",
    "NKG": "nanjing-china", "WEH": "weihai-china", "YNJ": "yanji-china",
    "CKG": "chongqing-china", "CSX": "changsha-china", "HGH": "hangzhou-china",
    "XMN": "xiamen-china", "TSN": "tianjin-china", "CGO": "zhengzhou-china",
    "WNZ": "wenzhou-china", "NGB": "ningbo-china", "HFE": "hefei-china",
    "TNA": "jinan-china", "CGQ": "changchun-china", "HAK": "haikou-china",
    "SYX": "sanya-china", "KWL": "guilin-china", "LJG": "lijiang-china",
    "CTU": "chengdu-china", "TFU": "chengdu-china", "URC": "urumqi-china",
    "HRB": "harbin-china", "JMU": "jiamusi-china", "MDG": "mudanjiang-china",
    "SZX": "shenzhen-china",
    # 대만·홍콩·마카오
    "TPE": "taipei-taiwan", "TSA": "taipei-taiwan", "KHH": "kaohsiung-taiwan",
    "RMQ": "taichung-taiwan", "HKG": "hong-kong", "MFM": "macau",
    # 동남아시아
    "BKK": "bangkok-thailand", "DMK": "bangkok-thailand", "HKT": "phuket-thailand",
    "CNX": "chiang-mai-thailand", "USM": "koh-samui-thailand", "HDY": "hat-yai-thailand",
    "SGN": "ho-chi-minh-city-vietnam", "HAN": "hanoi-vietnam", "DAD": "da-nang-vietnam",
    "CXR": "nha-trang-vietnam", "PQC": "phu-quoc-vietnam", "VTE": "vientiane-laos",
    "PNH": "phnom-penh-cambodia", "REP": "siem-reap-cambodia", "SIN": "singapore",
    "KUL": "kuala-lumpur-malaysia", "PEN": "penang-malaysia", "BKI": "kota-kinabalu-malaysia",
    "CGK": "jakarta-indonesia", "DPS": "denpasar-indonesia", "MNL": "manila-philippines",
    "CEB": "cebu-philippines", "KLO": "kalibo-philippines", "CRK": "angeles-philippines",
    "TAG": "tagbilaran-philippines", "RGN": "yangon-myanmar",
    # 태평양·오세아니아
    "GUM": "guam-united-states", "HNL": "honolulu-hawaii-united-states",
    "SYD": "sydney-australia", "MEL": "melbourne-australia", "BNE": "brisbane-australia",
    "OOL": "gold-coast-australia", "CNS": "cairns-australia", "AKL": "auckland-new-zealand",
    "NAN": "nadi-fiji",
    # 중앙아시아·몽골
    "UBN": "ulaanbaatar-mongolia", "ULN": "ulaanbaatar-mongolia",
    "ALA": "almaty-kazakhstan", "NQZ": "astana-kazakhstan", "TAS": "tashkent-uzbekistan",
    "FRU": "bishkek-kyrgyzstan", "DYU": "dushanbe-tajikistan",
    # 유럽
    "CDG": "paris-france", "ORY": "paris-france", "LHR": "london-united-kingdom",
    "LGW": "london-united-kingdom", "FCO": "rome-italy", "MXP": "milan-italy",
    "FRA": "frankfurt-germany", "MUC": "munich-germany", "BER": "berlin-germany",
    "AMS": "amsterdam-netherlands", "BCN": "barcelona-spain", "MAD": "madrid-spain",
    "VIE": "vienna-austria", "ZRH": "zurich-switzerland", "GVA": "geneva-switzerland",
    "PRG": "prague-czechia", "WAW": "warsaw-poland", "BUD": "budapest-hungary",
    "IST": "istanbul-turkey", "CPH": "copenhagen-denmark", "ARN": "stockholm-sweden",
    "OSL": "oslo-norway", "HEL": "helsinki-finland", "DUB": "dublin-ireland",
    "LIS": "lisbon-portugal", "ATH": "athens-greece",
    "SVO": "moscow-russia", "DME": "moscow-russia", "VKO": "moscow-russia",
    "LED": "saint-petersburg-russia", "VVO": "vladivostok-russia",
    # 미주
    "LAX": "los-angeles-california-united-states", "SFO": "san-francisco-california-united-states",
    "SEA": "seattle-washington-united-states", "JFK": "new-york-united-states",
    "EWR": "new-york-united-states", "LGA": "new-york-united-states",
    "ORD": "chicago-illinois-united-states", "DFW": "dallas-texas-united-states",
    "IAH": "houston-texas-united-states", "ATL": "atlanta-georgia-united-states",
    "BOS": "boston-massachusetts-united-states", "YYZ": "toronto-canada",
    "YVR": "vancouver-canada",
    # 중동·인도
    "DXB": "dubai-united-arab-emirates", "DOH": "doha-qatar", "DEL": "new-delhi-india",
    "BOM": "mumbai-india", "CMB": "colombo-sri-lanka", "KTM": "kathmandu-nepal",
    "DAC": "dhaka-bangladesh", "MLE": "male-maldives",
}



# ── OTA 검색 URL 빌더 ───────────────────────────────────────────────
def trip_url(dep: str, arr: str, depart: date, back: date | None) -> str:
    """트립닷컴 — 도시코드 대문자 (네이버 bookingUrl 과 동일 컨벤션, 실측 SEL/TYO)."""
    u = (f"https://kr.trip.com/flights/showfarefirst?dcity={_trip(dep)}&acity={_trip(arr)}"
         f"&ddate={_d(depart)}&triptype={'rt' if back else 'ow'}&class=y&quantity=1&searchboxarg=t")
    if back:
        u += f"&rdate={_d(back)}"
    return u


def myrealtrip_url(dep: str, arr: str, depart: date, back: date | None) -> str:
    """마이리얼트립 — 쿼리 파라미터 형식은 404 (실측 2026-10-19) → 항공 검색 루트로."""
    return "https://flights.myrealtrip.com/"


def nol_url(dep: str, arr: str, depart: date, back: date | None) -> str:
    u = f"https://air.nol.kr/international?dep={dep}&arr={arr}&depDate={_d(depart)}"
    if back:
        u += f"&retDate={_d(back)}"
    return u + "&adt=1"


def agoda_url(dep: str, arr: str, depart: date, back: date | None) -> str:
    """아고다 — 항공 검색 URL 파라미터 미지원, flights 랜딩으로."""
    return "https://www.agoda.com/ko-kr/flights"


def kiwi_url(dep: str, arr: str, depart: date, back: date | None) -> str:
    """Kiwi — /en/search/results/{도시-나라}/{도시-나라}/{날짜}/{날짜}/ (2026-10-19 실측).
    미등록 공항이면 홈(제휴쿠키는 설정됨, 직접 검색)."""
    d_slug, a_slug = KIWI_SLUG.get(dep), KIWI_SLUG.get(arr)
    if not d_slug or not a_slug:
        return "https://www.kiwi.com/en/"
    u = f"https://www.kiwi.com/en/search/results/{d_slug}/{a_slug}/{_d(depart)}"
    return u + f"/{_d(back)}/" if back else u + "/"


# ── 링크 조립 ────────────────────────────────────────────────────────
def lp_deeplink(merchant: str, target_url: str) -> str:
    """링크프라이스 딥링크 — l=9999 (사용자 정의 URL)."""
    return (f"https://click.linkprice.com/click.php?m={merchant}"
            f"&a={LP_AFFILIATE_ID}&l=9999&tu={quote(target_url, safe='')}")


def tp_link(brand_p: str, target_url: str) -> str:
    """트래블페이아웃 즉시 링크 (만료 없음, 쿠키 30일)."""
    return (f"https://tp.media/r?marker={TP_MARKER}&trs={TP_TRS}"
            f"&p={brand_p}&u={quote(target_url, safe='')}&sub_id={TP_SUB_ID}")


# ── 제휴 판매처 (네이버 partnerCode 기준) ─────────────────────────────
# 판매처를 추가/제외하려면 이 목록만 고친다. 수집기 필터·화면 뱃지·링크가 모두 여기서 나온다.
# 부킹닷컴(BDC219) — LP 에 없고 TP 미가입으로 제외 (2026-10-19)
@dataclass(frozen=True)
class Partner:
    code: str                                   # 네이버 partnerCode (CTR013)
    network: Literal["LP", "TP"]                # 링크프라이스 / 트래블페이아웃
    merchant: str                               # LP 머천트 ID 또는 TP 브랜드 p 값
    search_url: Callable[[str, str, date, Optional[date]], str]

    def link(self, dep: str, arr: str, depart: date, back: date | None) -> str:
        target = self.search_url(dep, arr, depart, back)
        return lp_deeplink(self.merchant, target) if self.network == "LP" else tp_link(self.merchant, target)


PARTNERS: dict[str, Partner] = {p.code: p for p in (
    Partner("CTR013", "LP", "ctrip", trip_url),          # 트립닷컴
    Partner("AGD217", "LP", "agoda", agoda_url),         # Agoda
    Partner("YNJ035", "LP", "yanolja", nol_url),         # NOL
    Partner("INT005", "LP", "yanolja", nol_url),         # NOL인터파크투어
    Partner("MRT023", "LP", "myrealtrip", myrealtrip_url),   # 마이리얼트립
    Partner("SKP206", "TP", TP_KIWI_P, kiwi_url),        # Kiwi.com 3%
)}


def affiliate_link(partner_code: str, dep: str, arr: str,
                   depart: date, back: date | None) -> str:
    """판매사 partnerCode + 노선 → 제휴 링크. 미지원 판매사면 빈 문자열."""
    p = PARTNERS.get(partner_code)
    return p.link(dep, arr, depart, back) if p else ""


__all__ = ["PARTNERS", "Partner", "affiliate_link", "lp_deeplink", "tp_link"]
