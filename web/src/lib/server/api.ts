// 서버 렌더링(SSR)에서 api 를 바로 부른다 — 브라우저는 vite 프록시(/api)로, 서버는 이 주소로.
import { API_URL } from '$app/env/private';

/** GET → JSON. 404 면 null, 그 밖의 실패는 예외 */
export async function apiGet<T>(path: string, fetcher: typeof fetch = fetch): Promise<T | null> {
	const r = await fetcher(`${API_URL}${path}`);
	if (r.status === 404) return null;
	if (!r.ok) throw new Error(`api ${path} → ${r.status}`);
	return (await r.json()) as T;
}
