<!--
  가격 달력 — 특가가 있는 날에만 그날 최저가(만원)를 보여 주고 고를 수 있게 한다.
  달은 특가가 있는 첫 달부터 마지막 달까지 세로로 이어 붙인다.
-->
<script lang="ts">
	import type { Facet } from '#lib/types.ts';

	let {
		days,
		value,
		min = '',
		onpick
	}: { days: Facet[]; value: string; min?: string; onpick: (date: string) => void } = $props();

	const WEEK = ['일', '월', '화', '수', '목', '금', '토'];
	const iso = (y: number, m: number, d: number) =>
		`${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;

	const byDate = $derived(new Map(days.map((f) => [f.value, f])));
	const cheapest = $derived(days.length ? Math.min(...days.map((f) => f.min_price)) : 0);

	// 특가가 있는 첫 달 ~ 마지막 달
	const months = $derived.by(() => {
		if (!days.length) return [];
		const first = days[0].value;
		const last = days[days.length - 1].value;
		let y = +first.slice(0, 4);
		let m = +first.slice(5, 7) - 1;
		const out: { y: number; m: number; blanks: number; count: number }[] = [];
		while (iso(y, m, 1) <= last.slice(0, 8) + '01') {
			out.push({ y, m, blanks: new Date(y, m, 1).getDay(), count: new Date(y, m + 1, 0).getDate() });
			m += 1;
			if (m === 12) {
				m = 0;
				y += 1;
			}
		}
		return out;
	});

	/** 151300 → "15.1" (만원) */
	const short = (n: number) => (Math.floor(n / 1000) / 10).toFixed(1).replace(/\.0$/, '');
</script>

<div class="calendar">
	<div class="week" aria-hidden="true">
		{#each WEEK as w, i (w)}<span class:sun={i === 0} class:sat={i === 6}>{w}</span>{/each}
	</div>
	{#each months as mo (`${mo.y}-${mo.m}`)}
		<section>
			<h4>{mo.y}년 {mo.m + 1}월</h4>
			<div class="grid">
				{#each Array(mo.blanks) as _, i (i)}<span></span>{/each}
				{#each Array(mo.count) as _, i (i)}
					{@const date = iso(mo.y, mo.m, i + 1)}
					{@const f = byDate.get(date)}
					{@const off = !f || (!!min && date <= min)}
					<button
						type="button"
						class="day"
						class:on={date === value}
						class:low={!!f && f.min_price === cheapest}
						disabled={off}
						aria-pressed={date === value}
						aria-label="{mo.m + 1}월 {i + 1}일{f ? ` 최저 ${f.min_price.toLocaleString('ko-KR')}원 ${f.count}개` : ''}"
						onclick={() => onpick(date === value ? '' : date)}
					>
						<b>{i + 1}</b>
						{#if f && !off}<small class="num">{short(f.min_price)}</small>{/if}
					</button>
				{/each}
			</div>
		</section>
	{/each}
</div>

<style>
	.calendar {
		padding: 4px 2px;
	}

	.week,
	.grid {
		display: grid;
		grid-template-columns: repeat(7, 1fr);
		text-align: center;
	}

	.week {
		position: sticky;
		top: -6px;
		z-index: 1;
		padding: 6px 0;
		background: #fff;
		color: var(--muted);
		font-size: 12px;
		font-weight: 600;
	}

	h4 {
		margin: 12px 4px 6px;
		font-size: 14px;
		font-weight: 700;
	}

	.day {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		height: 46px;
		margin: 1px;
		border: 0;
		border-radius: 10px;
		background: none;
		cursor: pointer;
		transition: background 0.15s;
	}

	.day b {
		font-size: 14px;
		font-weight: 600;
		line-height: 18px;
	}

	.day small {
		color: var(--sub);
		font-size: 10.5px;
		line-height: 14px;
	}

	.day.low small {
		color: var(--pt);
		font-weight: 700;
	}

	.day:hover:not(:disabled) {
		background: var(--hover);
	}

	.day:disabled {
		cursor: default;
	}

	.day:disabled b {
		color: var(--line);
		font-weight: 500;
	}

	.day.on {
		background: var(--ink);
	}

	.day.on b,
	.day.on small {
		color: #fff;
	}

</style>
