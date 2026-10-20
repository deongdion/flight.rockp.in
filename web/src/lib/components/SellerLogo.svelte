<!-- 판매처 아이콘 — 못 받으면 자리만 지킨다 -->
<script lang="ts">
	import { sellerLogo } from '#lib/format.ts';

	let { partnerCode, size = 16 }: { partnerCode: string; size?: number } = $props();

	let broken = $state(false);
	const src = $derived(sellerLogo(partnerCode));
</script>

<span class="logo" style:width="{size}px" style:height="{size}px" aria-hidden="true">
	{#if src && !broken}<img {src} alt="" loading="lazy" onerror={() => (broken = true)} />{/if}
</span>

<style>
	.logo {
		flex: none;
		display: inline-flex;
		border-radius: 4px;
		background: var(--el);
		overflow: hidden;
	}

	img {
		width: 100%;
		height: 100%;
		object-fit: contain;
		background: #fff;
	}
</style>
