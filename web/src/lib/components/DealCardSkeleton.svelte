<!-- 특가 카드 스켈레톤 — DealCard 와 같은 틀·크기 (다 그려졌을 때 자리가 튀지 않게) -->
<div class="card" aria-hidden="true">
	<div class="sk photo"></div>
	<div class="body">
		<div class="sk" style="width: 55%; height: 22px"></div>
		<div class="sk" style="width: 45%; height: 18px"></div>
		<div class="sk" style="width: 60%; height: 17px"></div>
		<div class="sk" style="width: 30%; height: 22px"></div>
		<div class="sk" style="width: 50%; height: 26px; margin-top: 8px"></div>
		<div class="btns">
			<div class="sk"></div>
			<div class="sk"></div>
		</div>
	</div>
</div>

<style>
	.card {
		border-radius: 18px;
		background: #fff;
		box-shadow: var(--card-shadow);
		overflow: hidden;
	}

	.photo {
		height: 150px;
		border-radius: 0;
	}

	.body {
		display: flex;
		flex-direction: column;
		gap: 7px;
		padding: 14px 16px 16px;
	}

	.btns {
		display: flex;
		gap: 6px;
		margin-top: 12px;
	}

	.btns .sk {
		flex: 1;
		height: 38px;
		border-radius: 11px;
	}
</style>
