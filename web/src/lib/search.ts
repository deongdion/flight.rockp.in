// 검색 조건 ↔ 주소 — /?from=SEL&to=NRT&depart=2026-10-30&return=2026-11-02&direct=1&sort=date (모두 선택 사항)
//   from·to·depart·return  서버가 DB 에서 찾는 조건
//   direct·sort             불러온 목록을 화면에서 거르고 정렬 (주소만 바꾸고 다시 불러오지 않는다)
import type { SearchFilters } from './types.ts';

const PARAMS: Record<keyof SearchFilters, string> = {
	origin: 'from',
	destination: 'to',
	departure_date: 'depart',
	return_date: 'return'
};

export function filtersFromURL(url: URL): SearchFilters {
	return Object.fromEntries(
		Object.entries(PARAMS).map(([key, param]) => [key, url.searchParams.get(param) ?? ''])
	) as unknown as SearchFilters;
}

export type ViewOptions = { directOnly: boolean; sort: 'price' | 'date' };

export function viewFromURL(url: { searchParams: { get(name: string): string | null } }): ViewOptions {
	return { directOnly: url.searchParams.get('direct') === '1', sort: url.searchParams.get('sort') === 'date' ? 'date' : 'price' };
}

/** 조건 → 화면 주소 ("/" 또는 "/?from=SEL&to=NRT&direct=1") */
export function searchHref(f: SearchFilters, view?: ViewOptions): string {
	const q = new URLSearchParams();
	for (const [key, param] of Object.entries(PARAMS)) {
		const value = f[key as keyof SearchFilters];
		if (value) q.set(param, value);
	}
	if (view?.directOnly) q.set('direct', '1');
	if (view?.sort === 'date') q.set('sort', 'date');
	const s = q.toString();
	return s ? `/?${s}` : '/';
}

/** 조건 → api 쿼리 (origin=SEL&destination=NRT…) */
export function apiQuery(f: SearchFilters): string {
	const q = new URLSearchParams();
	for (const [key, value] of Object.entries(f)) if (value) q.set(key, value);
	return q.toString();
}

export const EMPTY_FILTERS: SearchFilters = { origin: '', destination: '', departure_date: '', return_date: '' };

export const PAGE_SIZE = 24;

/** 화면용 특가 한 쪽 쿼리 (/api/deals) — 도착지를 안 골랐으면 도착지마다 최저 1건 */
export function pageQuery(f: SearchFilters, view: ViewOptions, offset: number): string {
	const q = new URLSearchParams(apiQuery(f));
	if (!f.destination) q.set('group', 'destination');
	if (view.directOnly) q.set('direct', 'true');
	if (view.sort === 'date') q.set('sort', 'date');
	q.set('offset', String(offset));
	q.set('limit', String(PAGE_SIZE));
	return q.toString();
}
