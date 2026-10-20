<!--
  가격 추이 — 이 노선(출발지 → 도착지)의 칸마다 최저가 (/api/prices).
    오늘: 한 시간 단위 · 7일 · 1개월: 하루 단위
  위: 가격 범위 바 — 기간 최저~최고 위에 "보통"(칸별 최저가의 가운데 50%) 구간을 진하게,
      지금 이 특가 가격을 점으로. 보통보다 아래면 "보통보다 싸요"(하늘색, 좋은 소식).
  아래: 막대 — 칸마다 그 칸 최저가. 지난 칸은 회색, 지금 칸은 하늘색과 가격.
  누르거나 마우스를 올리면 그 칸 날짜·가격. 특가가 사라져도 가격 기록은 남는다 (api/database.py prices).
-->
<script lang="ts">
	import { shortWon } from '#lib/format.ts';
	import type { PriceHistory } from '#lib/types.ts';

	let { origin, destination, price }: { origin: string; destination: string; price: number } = $props();

	const PERIODS = [
		['today', '오늘'],
		['7d', '7일'],
		['30d', '1개월']
	] as const;
	let period = $state<'today' | '7d' | '30d'>('7d');
	let history = $state<PriceHistory | null>(null);
	let failed = $state(false);
	let hover = $state<number | null>(null);

	$effect(() => {
		const q = new URLSearchParams({ destination, origin, period });
		const ctrl = new AbortController();
		failed = false;
		hover = null;
		fetch(`/api/prices?${q}`, { signal: ctrl.signal })
			.then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
			.then((h: PriceHistory) => (history = h))
			.catch((e) => e?.name !== 'AbortError' && (failed = true));
		return () => ctrl.abort();
	});

	const lows = $derived(history?.period === period ? history.points.map((p) => ({ t: p.t, v: p.min })) : []);
	const last = $derived(lows.length - 1);

	// 범위 — 기간 최저~최고(지금 가격 포함), 보통 = 칸별 최저가의 25~75%
	const range = $derived.by(() => {
		const vs = lows.map((p) => p.v).sort((a, b) => a - b);
		const q = (f: number) => vs[Math.min(vs.length - 1, Math.max(0, Math.round(f * (vs.length - 1))))];
		const min = Math.min(vs[0], price);
		const max = Math.max(vs[vs.length - 1], price);
		return { min, max, low: q(0.25), high: q(0.75) };
	});
	const pos = (v: number) => (range.max > range.min ? ((v - range.min) / (range.max - range.min)) * 100 : 50);
	const verdict = $derived(price < range.low ? 'cheap' : price > range.high ? 'pricey' : 'normal');

	// 막대 높이 — 바닥을 최저가보다 조금 아래로 잡아 차이가 보이게 (0원부터면 다 비슷해 보인다)
	const barHeight = (v: number) => {
		const base = range.min - (range.max - range.min) * 0.5 - 1;
		return 18 + ((v - base) / (range.max - base)) * 62; // 위 20%는 지금 가격 글자 자리
	};

	const tick = (t: string) => (t.includes('T') ? `${+t.slice(11, 13)}시` : `${+t.slice(5, 7)}.${+t.slice(8, 10)}`);
	const shown = $derived(hover !== null ? lows[hover] : null);
</script>

<section class="trend">
	<div class="head">
		<h3>가격 추이</h3>
		<div class="seg" role="radiogroup" aria-label="기간">
			{#each PERIODS as [value, label] (value)}
				<button role="radio" aria-checked={period === value} onclick={() => (period = value)}>{label}</button>
			{/each}
		</div>
	</div>

	{#if failed}
		<p class="empty">가격 추이를 불러오지 못했어요</p>
	{:else if !history || history.period !== period}
		<div class="sk chart-sk"></div>
	{:else if !lows.length}
		<p class="empty">이 기간 가격 기록이 아직 없어요</p>
	{:else}
		<!-- 가격 범위 -->
		<p class="verdict num">
			지금 <b>{shortWon(price)}</b> ·
			{#if verdict === 'cheap'}<b class="good">보통보다 싸요</b>
			{:else if verdict === 'pricey'}<b>보통보다 비싸요</b>
			{:else}<b>보통이에요</b>{/if}
		</p>
		<div class="range" aria-hidden="true">
			<span class="typical" style:left="{pos(range.low)}%" style:width="{Math.max(2, pos(range.high) - pos(range.low))}%"></span>
			<i class="me" class:good={verdict === 'cheap'} style:left="{pos(price)}%"></i>
		</div>
		<p class="range-text num">
			<span>최저 {shortWon(range.min)}</span>
			<span>보통 {shortWon(range.low)}~{shortWon(range.high)}</span>
			<span>최고 {shortWon(range.max)}</span>
		</p>

		<!-- 막대 — 칸마다 최저가 -->
		<div class="bars" role="img" aria-label="칸마다 최저가" onpointerleave={() => (hover = null)}>
			{#each lows as p, i (p.t)}
				<button
					type="button"
					class="bar"
					class:now={i === last}
					class:on={hover === i}
					aria-label="{tick(p.t)} 최저 {shortWon(p.v)}"
					onpointerenter={() => (hover = i)}
					onfocus={() => (hover = i)}
					onclick={() => (hover = i)}
				>
					<span style:height="{barHeight(p.v)}%">
						{#if i === last && hover === null}<em class="num">{shortWon(p.v)}</em>{/if}
					</span>
				</button>
			{/each}
		</div>
		<div class="axis num">
			<span>{tick(lows[0].t)}</span>
			<span class="at">{shown ? `${tick(shown.t)} 최저 ${shortWon(shown.v)}` : ''}</span>
			<span class="nowt">{period === 'today' ? '지금' : '오늘'}</span>
		</div>
	{/if}
</section>

<style>
	.head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		margin-bottom: 8px;
	}

	h3 {
		font-size: 15px;
		font-weight: 700;
	}

	.seg button {
		height: 26px;
		padding: 0 10px;
		font-size: 13px;
	}

	/* 가격 범위 */
	.verdict {
		font-size: 14px;
	}

	.good {
		color: var(--pt);
	}

	.range {
		position: relative;
		height: 6px;
		margin: 10px 0 6px;
		border-radius: 999px;
		background: var(--el);
	}

	.typical {
		position: absolute;
		top: 0;
		bottom: 0;
		border-radius: 999px;
		background: #c9ccd2;
	}

	.me {
		position: absolute;
		top: 50%;
		width: 14px;
		height: 14px;
		margin: -7px 0 0 -7px;
		border: 3px solid #fff;
		border-radius: 50%;
		background: var(--ink);
		box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.12);
	}

	.me.good {
		background: var(--pt);
	}

	.range-text {
		display: flex;
		justify-content: space-between;
		gap: 8px;
		color: var(--muted);
		font-size: 12px;
	}

	.range-text span:nth-child(2) {
		color: var(--sub);
	}

	/* 막대 */
	.bars {
		display: flex;
		align-items: flex-end;
		gap: 3px;
		height: 64px;
		margin-top: 14px;
		touch-action: pan-y;
	}

	.bar {
		flex: 1;
		min-width: 0;
		height: 100%;
		display: flex;
		align-items: flex-end;
		padding: 0;
		border: 0;
		background: none;
		cursor: pointer;
	}

	.bar span {
		position: relative;
		display: block;
		width: 100%;
		border-radius: 3px 3px 1px 1px;
		background: #dfe1e5;
		transition: background 0.12s;
	}

	.bar.on span {
		background: #b4b8bf;
	}

	/* 지금 — 하늘색 */
	.bar.now span {
		background: var(--pt);
	}

	.bar em {
		position: absolute;
		right: 0;
		bottom: calc(100% + 3px);
		color: var(--pt);
		font-size: 12px;
		font-style: normal;
		font-weight: 700;
		white-space: nowrap;
	}

	.axis {
		display: flex;
		justify-content: space-between;
		gap: 8px;
		margin-top: 4px;
		color: var(--muted);
		font-size: 12px;
	}

	.axis .at {
		color: var(--sub);
		text-align: center;
	}

	.axis .nowt {
		color: var(--pt);
	}

	.empty {
		padding: 22px 12px;
		border-radius: 14px;
		background: var(--hover);
		color: var(--sub);
		font-size: 13px;
		text-align: center;
	}

	.chart-sk {
		height: 150px;
		border-radius: 14px;
	}

	@media (max-height: 799px) {
		.head {
			margin-bottom: 4px;
		}

		.range {
			margin: 7px 0 4px;
		}

		.bars {
			height: 40px;
			margin-top: 8px;
		}

		.chart-sk {
			height: 116px;
		}
	}
</style>
