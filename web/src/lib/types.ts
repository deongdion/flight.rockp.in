// api 응답 모양 — api/schemas.py · core 의 Itinerary·Segment 와 같아야 한다.

export interface Segment {
	dep_airport: string;
	dep_date: string; // YYYYMMDD
	dep_time: string; // HHMM (현지)
	arr_airport: string;
	arr_date: string;
	arr_time: string;
	airline: string; // IATA
	flight_no: string;
}

export interface Itinerary {
	itinerary_id: string;
	duration: number; // 초, 경유 대기 포함
	segments: Segment[];
}

export interface Offer {
	partner_code: string; // 판매처 코드 (CTR013)
	seller: string; // 트립닷컴
	price: number; // 성인 1명 총액
	baggage: string; // FREE / CHARGE / UNKNOWN
	code: string; // 짧은 링크 코드 → /r/<code>
}

export interface Deal {
	origin: string; // 출발 도시 (SEL)
	destination: string; // 도착 공항 (NRT)
	destination_name: string; // 도쿄
	departure_date: string; // YYYY-MM-DD
	return_date: string | null;
	offers: Offer[]; // 싼 순
	itineraries: Itinerary[]; // 가는편[, 오는편]
	image_url: string | null; // 도착 도시 사진
	country_code: string | null; // 도착 나라 (JP, CN …)
	checked_at: string; // ISO 8601
}

/** 짧은 링크 1개 — 판매처 요금 1건을 모을 때 본 그대로 */
export interface Link {
	code: string;
	origin: string; // 출발 공항 (ICN)
	destination: string;
	destination_name: string;
	departure_date: string;
	return_date: string | null;
	offer: Offer; // 모을 때 가격
	itineraries: Itinerary[];
	image_url: string | null;
	checked_at: string;
}

/** 예약 버튼 클릭 시점 실시간 확인 결과 */
export interface RedirectLink {
	url: string;
	price: number | null;
	kind: 'booking' | 'search';
	itineraries: Itinerary[]; // 실시간 확인한 항공편
	sold_out: boolean; // 조회는 됐지만 이 판매처 요금이 없다
}

/** 검색 조건 — 넷 다 선택 사항 (빈 문자열이면 조건 없음) */
export interface SearchFilters {
	origin: string; // 출발 도시 (SEL)
	destination: string; // 도착 공항 (NRT)
	departure_date: string; // YYYY-MM-DD
	return_date: string;
}

/** 조건 값 하나의 집계 — 특가 수·최저가 (/api/deals/facets) */
export interface Facet {
	value: string;
	count: number;
	min_price: number;
	name?: string; // 도착지 이름 (destination 만)
	country?: string | null; // 도착 나라 (destination 만)
}

export type Facets = Record<keyof SearchFilters, Facet[]>;

/** 가격 추이 캔들 한 칸 — 하루(YYYY-MM-DD) 또는 한 시간(YYYY-MM-DDTHH), 한국 시각 */
export interface PricePoint {
	t: string;
	open: number; // 첫 가격
	close: number; // 마지막 가격
	min: number;
	max: number;
	avg: number;
	count: number; // 관측 수
}

/** 가격 추이 (/api/prices) */
export interface PriceHistory {
	period: 'today' | '7d' | '30d';
	points: PricePoint[];
	min: number | null; // 기간 전체
	avg: number | null;
	max: number | null;
}

/** 특가 한 쪽 (/api/deals) */
export interface DealPage {
	total: number; // 조건에 맞는 개수 (도착지마다 묶으면 도착지 수)
	deal_count: number; // 특가 수 (묶지 않고)
	items: Deal[];
}
