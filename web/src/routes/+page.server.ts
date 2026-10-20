import { filtersFromURL, pageQuery, viewFromURL } from '#lib/search.ts';
import { apiGet } from '#lib/server/api.ts';
import type { DealPage } from '#lib/types.ts';
import type { PageServerLoad } from './$types';

// 첫 한 쪽(24장)만 서버에서 그려 보낸다 — 나머지는 스크롤하면 브라우저가 /api/deals 로 이어 받는다.
// 검색 상자의 도착지·날짜 목록(facets, 60KB)은 HTML 에 넣지 않고 검색 상자를 쓰려 할 때 받는다 (SearchBox)
export const load: PageServerLoad = async ({ url, fetch, setHeaders }) => {
	setHeaders({ 'cache-control': 'public, max-age=60' });
	const filters = filtersFromURL(url);
	const view = viewFromURL(url);
	// 도착지를 안 골랐으면 도착지마다 최저 1건 (같은 도착지가 날짜만 바꿔 목록을 채우지 않게)
	const grouped = !filters.destination;

	try {
		const page = await apiGet<DealPage>(`/api/deals?${pageQuery(filters, view, 0)}`, fetch);
		return {
			deals: page?.items ?? [],
			total: page?.total ?? 0,
			dealCount: page?.deal_count ?? 0,
			filters,
			view,
			grouped,
			error: ''
		};
	} catch {
		return { deals: null, total: 0, dealCount: 0, filters, view, grouped, error: 'unavailable' };
	}
};
