<!-- 판매처 1곳: 이름 · 꼬리표 · 가격 · [예약하기] → 짧은 링크 /r/<code> (클릭 시점 실시간 재확인) -->
<script lang="ts">
	import SellerLogo from './SellerLogo.svelte';
	import { won } from '#lib/format.ts';
	import type { Offer } from '#lib/types.ts';

	let { offer, href, cheapest = false }: { offer: Offer; href: string; cheapest?: boolean } = $props();
</script>

<div class="offer">
	<div class="seller">
		<SellerLogo partnerCode={offer.partner_code} size={20} />
		<strong>{offer.seller}</strong>
		<span class="tags">
			{#if cheapest}<span class="tag">최저가</span>{/if}
			{#if offer.baggage === 'CHARGE'}<span class="tag calm">수화물 별도</span>{/if}
		</span>
	</div>
	<span class="price num">{won(offer.price)}</span>
	<a class="btn" class:primary={cheapest} {href} target="_blank" rel="noopener">예약하기</a>
</div>

<style>
	.offer {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 10px 12px;
		border-radius: 10px;
		transition: background 0.15s;
	}

	.offer:hover {
		background: var(--hover);
	}

	.seller {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 4px 8px;
	}

	.seller strong {
		font-size: 14px;
		font-weight: 600;
	}

	.tags {
		min-height: 0;
	}

	.price {
		font-size: 15px;
		font-weight: 700;
		white-space: nowrap;
	}

	.btn {
		height: 34px;
		padding: 0 14px;
	}
</style>
