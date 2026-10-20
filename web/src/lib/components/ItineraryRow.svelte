<!-- 가는편/오는편 1줄: 항공사 로고 · 출발→도착 시각(+1) · 공항·편명 · 소요시간 · 직항/경유 -->
<script lang="ts">
	import { airlineLogo, dayOffset, duration, hhmm, stops } from '#lib/format.ts';
	import type { Itinerary } from '#lib/types.ts';

	let { itinerary, label }: { itinerary: Itinerary; label?: string } = $props();

	const first = $derived(itinerary.segments[0]);
	const last = $derived(itinerary.segments.at(-1));
	const airlines = $derived([...new Set(itinerary.segments.map((s) => s.airline))]);
	const plusDays = $derived(dayOffset(itinerary));
	const via = $derived(stops(itinerary));
</script>

{#if first && last}
	<div class="row">
		{#if label}<span class="label">{label}</span>{/if}
		<span class="logos">
			{#each airlines as code (code)}
				<img src={airlineLogo(code)} alt={code} onerror={(e) => e.currentTarget.remove()} />
			{/each}
		</span>
		<span class="times num">
			{hhmm(first.dep_time)} – {hhmm(last.arr_time)}{#if plusDays}<sup>+{plusDays}</sup>{/if}
		</span>
		<span class="duration">{duration(itinerary.duration)} · {via ? `경유 ${via}회` : '직항'}</span>
		<span class="meta">
			{first.dep_airport} → {last.arr_airport} · {itinerary.segments.map((s) => s.airline + s.flight_no).join(', ')}
		</span>
	</div>
{/if}

<style>
	.row {
		display: grid;
		grid-template-columns: auto auto 1fr auto;
		grid-template-areas:
			'label logos times duration'
			'label logos meta meta';
		align-items: center;
		column-gap: 10px;
		padding: 5px 0;
	}

	.label {
		grid-area: label;
		width: 2.6em;
		color: var(--muted);
		font-size: 12px;
	}

	.logos {
		grid-area: logos;
		display: flex;
		gap: 2px;
		min-width: 20px;
	}

	.logos img {
		width: 20px;
		height: 20px;
		object-fit: contain;
	}

	.times {
		grid-area: times;
		font-size: 15px;
		font-weight: 700;
	}

	sup {
		margin-left: 1px;
		color: var(--sub);
		font-size: 10px;
	}

	.duration {
		grid-area: duration;
		color: var(--sub);
		font-size: 13px;
		white-space: nowrap;
	}

	.meta {
		grid-area: meta;
		color: var(--muted);
		font-size: 12px;
	}
</style>
