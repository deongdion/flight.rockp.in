import { defineEnvVars } from '@sveltejs/kit/env';

// 환경 변수 — 없으면 기본값. public 은 $app/env/public, 나머지는 서버 전용 $app/env/private 로 쓴다
export const variables = defineEnvVars({
	PUBLIC_SITE_URL: {
		public: true,
		description: '사이트 주소 (OG·canonical·sitemap 의 절대 주소)',
		schema: (v) => (v || 'https://flight.rockp.in').replace(/\/$/, '')
	},
	API_URL: {
		description: '서버 렌더링에서 부르는 api 주소',
		schema: (v) => (v || 'http://127.0.0.1:8000').replace(/\/$/, '')
	}
});
