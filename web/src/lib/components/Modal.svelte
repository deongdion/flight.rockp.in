<!--
  모달 / 바텀시트 (DESIGN.md 6번).
  넓은 화면: 가운데 흰 판(최대 440px, wide 면 520px). 640px 이하: 아래에서 올라오는 시트(손잡이, 안에서만 스크롤).
  Esc·바깥 누르기로 닫고, 닫으면 원래 누른 곳으로 포커스를 돌려준다. 열려 있는 동안 뒤 스크롤 잠금.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import Caret from './Caret.svelte';

	let {
		title,
		wide = false,
		onclose,
		children,
		footer
	}: { title: string; wide?: boolean; onclose: () => void; children: Snippet; footer?: Snippet } = $props();

	let panel: HTMLDivElement;

	$effect(() => {
		const opener = document.activeElement as HTMLElement | null;
		const overflow = document.body.style.overflow;
		document.body.style.overflow = 'hidden';
		panel.focus();
		return () => {
			document.body.style.overflow = overflow;
			opener?.focus();
		};
	});
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && onclose()} />

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
<div class="scrim" onclick={onclose}>
	<div
		class="panel"
		class:wide
		role="dialog"
		aria-modal="true"
		aria-label={title}
		tabindex="-1"
		bind:this={panel}
		onclick={(e) => e.stopPropagation()}
	>
		<div class="handle" aria-hidden="true"></div>
		<header>
			<h2>{title}</h2>
			<button class="close" onclick={onclose} aria-label="닫기"><Caret kind="close" /></button>
		</header>
		<div class="body">{@render children()}</div>
		{#if footer}<footer>{@render footer()}</footer>{/if}
	</div>
</div>

<style>
	.scrim {
		position: fixed;
		inset: 0;
		z-index: 50;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: var(--gut);
		background: rgba(0, 0, 0, 0.32);
		animation: fade 0.22s var(--ease);
	}

	.panel {
		display: flex;
		flex-direction: column;
		width: 100%;
		max-width: 440px;
		max-height: min(720px, calc(100dvh - 2 * var(--gut)));
		border-radius: 22px;
		background: #fff;
		outline: none;
		animation: rise 0.22s var(--ease);
	}

	.panel.wide {
		max-width: 520px;
		max-height: calc(100dvh - 2 * var(--gut));
	}

	.handle {
		display: none;
	}

	header {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 22px 24px 4px;
	}

	h2 {
		flex: 1;
		font-size: 18px;
		font-weight: 700;
		letter-spacing: -0.01em;
	}

	.close {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 36px;
		height: 36px;
		margin-right: -8px;
		border: 0;
		border-radius: 999px;
		background: none;
		color: var(--sub);
		cursor: pointer;
		transition: background 0.15s;
	}

	.close:hover {
		background: var(--el);
		color: #000;
	}

	.close :global(.caret) {
		width: 14px;
		height: 14px;
	}

	.body {
		padding: 12px 24px 20px;
		overflow-y: auto;
		overscroll-behavior: contain;
	}

	footer {
		display: flex;
		gap: 8px;
		padding: 0 24px 24px;
	}

	footer :global(.btn) {
		flex: 1;
	}

	footer :global(.btn.primary) {
		flex: 1.4;
	}

	@keyframes fade {
		from {
			opacity: 0;
		}
	}

	@keyframes rise {
		from {
			opacity: 0;
			transform: translateY(8px);
		}
	}

	@keyframes sheet {
		from {
			transform: translateY(100%);
		}
	}

	@media (max-width: 640px) {
		.scrim {
			align-items: flex-end;
			padding: 0;
		}

		.panel,
		.panel.wide {
			max-width: none;
			max-height: 96dvh;
			border-radius: 22px 22px 0 0;
			padding-bottom: env(safe-area-inset-bottom);
			animation: sheet 0.3s var(--ease);
		}

		.handle {
			display: block;
			width: 36px;
			height: 4px;
			margin: 8px auto 0;
			border-radius: 999px;
			background: var(--line);
		}

		header {
			padding: 10px 20px 0;
		}

		.body {
			padding: 8px 20px 12px;
		}

		footer {
			padding: 0 20px 16px;
		}
	}
</style>
