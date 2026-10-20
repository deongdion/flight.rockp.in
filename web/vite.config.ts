import adapter from '@sveltejs/adapter-auto';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig, type ServerOptions } from 'vite';

// 개발(npm run dev)과 배포 미리보기(npm run preview) 공용
const serve: ServerOptions = {
	host: '0.0.0.0', // 사내에서 접속 (http://<이 PC IP>:5173)
	port: 5173,
	// Cloudflare 터널(flight.rockp.in)·ngrok 으로 밖에서 열 때 — vite 는 모르는 Host 요청을 막는다
	allowedHosts: ['.rockp.in', '.ngrok-free.app', '.ngrok-free.dev', '.ngrok.app', '.ngrok.dev'],
	// api (Litestar) 로 넘긴다 — api 는 이 PC 안에서만 열고 밖에서는 이 프록시로만 들어온다
	proxy: { '/api': 'http://127.0.0.1:8000' }
};

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},

			// adapter-auto only supports some environments, see https://svelte.dev/docs/kit/adapter-auto for a list.
			// If your environment is not supported, or you settled on a specific environment, switch out the adapter.
			// See https://svelte.dev/docs/kit/adapters for more information about adapters.
			adapter: adapter()
		})
	],
	server: serve,
	// 밖에 공유할 때는 빌드본으로 — 개발 모드는 파일 수백 개를 따로 보내 ngrok 너머에서 느리다
	preview: serve
});
