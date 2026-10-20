<script lang="ts">
	import '../app.css';
	import Logo from '#lib/components/Logo.svelte';
	import { page } from '$app/state';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();
	// 예약 이동 화면은 위 막대 없이 꽉 채운다
	const bare = $derived(page.url.pathname.startsWith('/r/'));
</script>

<svelte:head>
	<!-- 아이콘: 탭은 svg, ico 를 찾는 곳(새 탭 바로가기·즐겨찾기·검색 결과)은 favicon.ico, 홈 화면은 png -->
	<link rel="icon" href="/favicon.ico" sizes="48x48" />
	<link rel="icon" href="/icon.svg" type="image/svg+xml" />
	<link rel="apple-touch-icon" href="/apple-touch-icon.png" />
</svelte:head>

{#if bare}
	{@render children()}
{:else}
	<header class="top">
		<a class="home" href="/" aria-label="록핀 처음 화면"><Logo /></a>
		<h1 class="title">오늘의 급락 항공권</h1>
	</header>

	<main>{@render children()}</main>
{/if}

<style>
	/* 위 막대 — 바탕만 화면 끝까지, 내용은 --max 폭에 맞춘다. 선·그림자 없음, 함께 스크롤 */
	.top {
		display: flex;
		align-items: center;
		gap: 14px;
		height: var(--top);
		padding: 0 max(var(--gut), calc(50% - var(--max) / 2 + var(--gut)));
		background: #fff;
	}

	.home {
		display: inline-flex;
		width: 72px;
		color: #2f2f2f;
		border-radius: 6px;
		transition: color 0.15s;
	}

	.home:hover {
		color: #000;
	}

	.title {
		color: var(--sub);
		font-size: 15px;
		font-weight: 600;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	/* 남는 높이를 채운다 — 빈 화면 안내가 남는 공간 가운데에 오도록 */
	main {
		display: flex;
		flex-direction: column;
		min-height: calc(100dvh - var(--top));
		padding-bottom: calc(56px + env(safe-area-inset-bottom));
	}

	main > :global(.wrap) {
		flex: 1;
		display: flex;
		flex-direction: column;
		width: 100%;
	}
</style>
