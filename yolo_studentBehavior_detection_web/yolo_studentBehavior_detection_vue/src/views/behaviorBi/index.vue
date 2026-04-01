<template>
	<div class="behavior-bi-page">
		<section class="bi-header">
			<div>
				<h2 class="bi-title">学生行为分析看板</h2>
				<p class="bi-subtitle">每 {{ refreshSeconds }} 秒自动刷新，持续追踪课堂专注度、活跃度与风险变化</p>
			</div>
			<div class="bi-actions">
				<div class="live-badge">
					<span class="live-dot" :class="{ offline: apiOnline === false }" />
					<span>实时</span>
				</div>
				<div class="last-updated">更新时间：{{ lastUpdatedText }}</div>
				<el-button class="refresh-btn" type="primary" :loading="isLoading" @click="handleManualRefresh">立即刷新</el-button>
			</div>
		</section>

		<section class="kpi-grid">
			<article class="kpi-item">
				<div class="kpi-label">最新课堂人数</div>
				<div class="kpi-value">{{ latestCounts.studentCount }}</div>
			</article>
			<article class="kpi-item">
				<div class="kpi-label">当前专注度</div>
				<div class="kpi-value">{{ latestFocusScore }}</div>
			</article>
			<article class="kpi-item">
				<div class="kpi-label">平均活跃度</div>
				<div class="kpi-value">{{ averageActivityScore }}</div>
			</article>
			<article class="kpi-item">
				<div class="kpi-label">当前异常率</div>
				<div class="kpi-value">{{ latestCounts.abnormalRate }}%</div>
			</article>
			<article class="kpi-item">
				<div class="kpi-label">风险等级</div>
				<div class="kpi-value">{{ riskLevelText }}</div>
			</article>
		</section>

		<section class="charts-grid">
			<article class="panel panel-wide">
				<header class="panel-header">
					<h3>专注度与活跃度趋势</h3>
				</header>
				<div class="panel-chart" ref="trendChartRef" />
			</article>

			<article class="panel panel-compact">
				<header class="panel-header">
					<h3>最新行为占比</h3>
				</header>
				<div class="panel-chart panel-chart-compact" ref="pieChartRef" />
			</article>

			<article class="panel panel-compact">
				<header class="panel-header">
					<h3>实时专注度仪表盘</h3>
				</header>
				<div class="panel-chart panel-chart-compact" ref="gaugeChartRef" />
			</article>

			<article class="panel panel-wide">
				<header class="panel-header">
					<h3>课堂风险热力图（按周/小时）</h3>
				</header>
				<div class="panel-chart" ref="heatmapChartRef" />
			</article>

			<article class="panel panel-full">
				<header class="panel-header">
					<h3>不良行为人数变化</h3>
				</header>
				<div class="panel-chart" ref="stackChartRef" />
			</article>
		</section>
	</div>
</template>

<script lang="ts" setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import axios from 'axios';
import * as echarts from 'echarts';

type BehaviorItem = {
	id?: number;
	classroomId?: string;
	recordTime?: string | Date;
	studentCount?: number;
	focusScore?: number;
	activityScore?: number;
	interactionLevel?: string;
	metricsJson?: string;
	risksJson?: string;
};

type BehaviorCounts = {
	headDown: number;
	phone: number;
	sleeping: number;
	normal: number;
	studentCount: number;
	abnormalRate: number;
};

type ChartKey = 'trend' | 'stack' | 'pie' | 'gauge' | 'heatmap';

const REFRESH_INTERVAL_MS = 5000;
const MAX_RECORDS = 72;

const trendChartRef = ref<HTMLElement | null>(null);
const stackChartRef = ref<HTMLElement | null>(null);
const pieChartRef = ref<HTMLElement | null>(null);
const gaugeChartRef = ref<HTMLElement | null>(null);
const heatmapChartRef = ref<HTMLElement | null>(null);

const records = ref<BehaviorItem[]>([]);
const isLoading = ref(false);
const apiOnline = ref<boolean | null>(null);
const lastUpdatedAt = ref<Date | null>(null);

let chartInstances: Partial<Record<ChartKey, echarts.ECharts>> = {};
let refreshTimer: ReturnType<typeof setInterval> | null = null;
let pageAlive = true;
let isFetching = false;

const refreshSeconds = Math.round(REFRESH_INTERVAL_MS / 1000);

const safeNumber = (value: unknown, fallback = 0) => {
	const n = Number(value);
	return Number.isFinite(n) ? n : fallback;
};

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

const parseJsonObject = (raw: unknown): Record<string, unknown> => {
	if (raw && typeof raw === 'object') return raw as Record<string, unknown>;
	if (typeof raw !== 'string' || !raw.trim()) return {};
	try {
		return JSON.parse(raw) as Record<string, unknown>;
	} catch {
		return {};
	}
};

const pickFirstNumber = (obj: Record<string, unknown>, keys: string[], fallback = 0) => {
	for (const key of keys) {
		const value = safeNumber(obj[key], NaN);
		if (Number.isFinite(value)) return value;
	}
	return fallback;
};

const toDate = (value: BehaviorItem['recordTime']) => {
	if (value instanceof Date) return value;
	if (typeof value === 'string' && value.trim()) {
		const normalized = value.includes('T') ? value : value.replace(' ', 'T');
		const date = new Date(normalized);
		if (!Number.isNaN(date.getTime())) return date;
	}
	return new Date();
};

const formatDateLabel = (value: BehaviorItem['recordTime']) => {
	const date = toDate(value);
	const month = `${date.getMonth() + 1}`.padStart(2, '0');
	const day = `${date.getDate()}`.padStart(2, '0');
	const hour = `${date.getHours()}`.padStart(2, '0');
	const minute = `${date.getMinutes()}`.padStart(2, '0');
	return `${month}-${day} ${hour}:${minute}`;
};

const formatDateTime = (value: Date | null) => {
	if (!value) return '--';
	const month = `${value.getMonth() + 1}`.padStart(2, '0');
	const day = `${value.getDate()}`.padStart(2, '0');
	const hour = `${value.getHours()}`.padStart(2, '0');
	const minute = `${value.getMinutes()}`.padStart(2, '0');
	const second = `${value.getSeconds()}`.padStart(2, '0');
	return `${month}-${day} ${hour}:${minute}:${second}`;
};

const calculateCounts = (item: BehaviorItem): BehaviorCounts => {
	const metrics = parseJsonObject(item.metricsJson);
	const students = Math.max(0, Math.round(safeNumber(item.studentCount, 0)));

	const headDown = Math.max(
		0,
		Math.round(
			pickFirstNumber(metrics, ['head_down_count', 'headDownCount'], (students * pickFirstNumber(metrics, ['head_down_rate', 'headDownRate'], 0)) / 100)
		)
	);

	const phone = Math.max(
		0,
		Math.round(
			pickFirstNumber(metrics, ['phone_usage_count', 'phoneUsageCount'], (students * pickFirstNumber(metrics, ['phone_usage_rate', 'phoneUsageRate'], 0)) / 100)
		)
	);

	const sleeping = Math.max(
		0,
		Math.round(
			pickFirstNumber(metrics, ['sleeping_count', 'sleepingCount'], (students * pickFirstNumber(metrics, ['sleeping_rate', 'sleepingRate'], 0)) / 100)
		)
	);

	const abnormalCount = headDown + phone + sleeping;
	const normal = Math.max(0, students - abnormalCount);
	const abnormalRate = students > 0 ? Number(((abnormalCount / students) * 100).toFixed(1)) : 0;

	return {
		headDown,
		phone,
		sleeping,
		normal,
		studentCount: students,
		abnormalRate,
	};
};

const calculateRiskScore = (item: BehaviorItem) => {
	const risks = parseJsonObject(item.risksJson);
	const values = Object.values(risks)
		.map((value) => safeNumber(value, NaN))
		.filter((value) => Number.isFinite(value)) as number[];

	const directRisk = pickFirstNumber(risks, ['overall_risk', 'overallRisk', 'risk_index', 'riskIndex', 'risk_score', 'riskScore'], NaN);
	if (Number.isFinite(directRisk)) return clamp(directRisk, 0, 100);
	if (values.length > 0) return clamp(values.reduce((sum, n) => sum + n, 0) / values.length, 0, 100);

	return clamp(calculateCounts(item).abnormalRate * 1.8, 0, 100);
};

const recentRecords = computed(() => records.value.slice(-MAX_RECORDS));
const latestRecord = computed(() => recentRecords.value[recentRecords.value.length - 1] ?? null);
const latestCounts = computed(() => (latestRecord.value ? calculateCounts(latestRecord.value) : calculateCounts({ studentCount: 0 })));

const latestFocusScore = computed(() => Math.round(safeNumber(latestRecord.value?.focusScore, 0)));

const averageActivityScore = computed(() => {
	if (!recentRecords.value.length) return 0;
	const total = recentRecords.value.reduce((sum, item) => sum + safeNumber(item.activityScore, 0), 0);
	return Number((total / recentRecords.value.length).toFixed(1));
});

const riskLevelText = computed(() => {
	const abnormalRate = latestCounts.value.abnormalRate;
	if (abnormalRate >= 45) return '高风险';
	if (abnormalRate >= 25) return '中风险';
	return '低风险';
});

const lastUpdatedText = computed(() => formatDateTime(lastUpdatedAt.value));

const ensureChart = (key: ChartKey, el: HTMLElement) => {
	const existing = chartInstances[key];
	if (existing && !existing.isDisposed()) return existing;
	const instance = echarts.init(el);
	chartInstances[key] = instance;
	return instance;
};

const disposeCharts = () => {
	Object.values(chartInstances).forEach((chart) => chart?.dispose());
	chartInstances = {};
};

const updateTrendChart = (chart: echarts.ECharts, data: BehaviorItem[]) => {
	const labels = data.map((item) => formatDateLabel(item.recordTime));
	const focusSeries = data.map((item) => clamp(safeNumber(item.focusScore, 0), 0, 100));
	const activitySeries = data.map((item) => clamp(safeNumber(item.activityScore, 0), 0, 100));
	const abnormalSeries = data.map((item) => calculateCounts(item).abnormalRate);

	chart.setOption(
		{
			color: ['#1d4ed8', '#0891b2', '#f97316'],
			tooltip: { trigger: 'axis' },
			legend: { top: 4, data: ['专注度', '活跃度', '异常率'] },
			grid: { left: 48, right: 42, top: 46, bottom: 30 },
			xAxis: { type: 'category', boundaryGap: false, data: labels, axisLabel: { color: '#64748b' } },
			yAxis: [
				{ type: 'value', min: 0, max: 100, name: '评分', axisLabel: { color: '#64748b' } },
				{ type: 'value', min: 0, max: 100, name: '异常率%', axisLabel: { color: '#64748b' } },
			],
			series: [
				{
					name: '专注度',
					type: 'line',
					data: focusSeries,
					smooth: true,
					symbol: 'none',
					lineStyle: { width: 2.5 },
					areaStyle: {
						color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
							{ offset: 0, color: 'rgba(29, 78, 216, 0.28)' },
							{ offset: 1, color: 'rgba(29, 78, 216, 0.02)' },
						]),
					},
				},
				{
					name: '活跃度',
					type: 'line',
					data: activitySeries,
					smooth: true,
					symbol: 'none',
					lineStyle: { width: 2, type: 'dashed' },
				},
				{
					name: '异常率',
					type: 'bar',
					yAxisIndex: 1,
					data: abnormalSeries,
					barMaxWidth: 12,
					itemStyle: { opacity: 0.85, borderRadius: [4, 4, 0, 0] },
				},
			],
		},
		true
	);
};

const updateStackChart = (chart: echarts.ECharts, data: BehaviorItem[]) => {
	const labels = data.map((item) => formatDateLabel(item.recordTime));
	const headDownSeries = data.map((item) => calculateCounts(item).headDown);
	const phoneSeries = data.map((item) => calculateCounts(item).phone);
	const sleepingSeries = data.map((item) => calculateCounts(item).sleeping);

	chart.setOption(
		{
			color: ['#f97316', '#ef4444', '#8b5cf6'],
			tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
			legend: { top: 4, data: ['低头', '玩手机', '睡觉'] },
			grid: { left: 50, right: 18, top: 46, bottom: 30 },
			xAxis: { type: 'category', data: labels, axisLabel: { color: '#64748b' } },
			yAxis: { type: 'value', name: '人数', axisLabel: { color: '#64748b' } },
			series: [
				{ name: '低头', type: 'bar', stack: 'abnormal', data: headDownSeries, barMaxWidth: 14 },
				{ name: '玩手机', type: 'bar', stack: 'abnormal', data: phoneSeries, barMaxWidth: 14 },
				{ name: '睡觉', type: 'bar', stack: 'abnormal', data: sleepingSeries, barMaxWidth: 14 },
			],
		},
		true
	);
};

const updatePieChart = (chart: echarts.ECharts, latest: BehaviorItem | null) => {
	const counts = latest ? calculateCounts(latest) : calculateCounts({ studentCount: 0 });

	chart.setOption(
		{
			color: ['#0ea5e9', '#f97316', '#ef4444', '#16a34a'],
			tooltip: { trigger: 'item' },
			legend: { bottom: 0, icon: 'circle' },
			series: [
				{
					type: 'pie',
					radius: ['45%', '72%'],
					center: ['50%', '45%'],
					avoidLabelOverlap: false,
					label: { show: false },
					data: [
						{ name: '低头', value: counts.headDown },
						{ name: '玩手机', value: counts.phone },
						{ name: '睡觉', value: counts.sleeping },
						{ name: '正常听讲', value: counts.normal },
					],
				},
			],
		},
		true
	);
};

const updateGaugeChart = (chart: echarts.ECharts, latest: BehaviorItem | null) => {
	const focus = clamp(Math.round(safeNumber(latest?.focusScore, 0)), 0, 100);

	chart.setOption(
		{
			series: [
				{
					type: 'gauge',
					min: 0,
					max: 100,
					progress: { show: true, width: 16, roundCap: true },
					axisLine: { lineStyle: { width: 16 } },
					axisTick: { show: false },
					splitLine: { length: 10, lineStyle: { width: 2 } },
					axisLabel: { color: '#64748b' },
					pointer: { show: true, itemStyle: { color: '#1d4ed8' } },
					anchor: { show: true, size: 10, itemStyle: { color: '#1d4ed8' } },
					title: { offsetCenter: [0, '72%'], color: '#475569' },
					detail: { valueAnimation: true, formatter: '{value} 分', color: '#0f172a', fontSize: 24, offsetCenter: [0, '35%'] },
					data: [{ value: focus, name: '课堂专注度' }],
				},
			],
		},
		true
	);
};

const updateHeatmapChart = (chart: echarts.ECharts, data: BehaviorItem[]) => {
	const days = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
	const hours = Array.from({ length: 24 }, (_, index) => `${`${index}`.padStart(2, '0')}:00`);
	const sums: number[][] = Array.from({ length: 7 }, () => Array.from({ length: 24 }, () => 0));
	const counts: number[][] = Array.from({ length: 7 }, () => Array.from({ length: 24 }, () => 0));

	data.forEach((item) => {
		const date = toDate(item.recordTime);
		const dayIndex = (date.getDay() + 6) % 7;
		const hourIndex = date.getHours();
		sums[dayIndex][hourIndex] += calculateRiskScore(item);
		counts[dayIndex][hourIndex] += 1;
	});

	const heatmapData: number[][] = [];
	for (let day = 0; day < 7; day += 1) {
		for (let hour = 0; hour < 24; hour += 1) {
			const value = counts[day][hour] > 0 ? Number((sums[day][hour] / counts[day][hour]).toFixed(1)) : 0;
			heatmapData.push([hour, day, value]);
		}
	}

	chart.setOption(
		{
			tooltip: { position: 'top', formatter: (params: any) => `${days[params.value[1]]} ${hours[params.value[0]]}<br/>风险指数：${params.value[2]}` },
			grid: { left: 52, right: 18, top: 22, bottom: 40 },
			xAxis: { type: 'category', data: hours, splitArea: { show: true }, axisLabel: { color: '#64748b', interval: 2 } },
			yAxis: { type: 'category', data: days, splitArea: { show: true }, axisLabel: { color: '#64748b' } },
			visualMap: {
				min: 0,
				max: 100,
				calculable: true,
				orient: 'horizontal',
				left: 'center',
				bottom: 0,
				inRange: {
					color: ['#e0f2fe', '#7dd3fc', '#38bdf8', '#0ea5e9', '#0284c7'],
				},
			},
			series: [{ type: 'heatmap', data: heatmapData, emphasis: { itemStyle: { shadowBlur: 8, shadowColor: 'rgba(15, 23, 42, 0.35)' } } }],
		},
		true
	);
};

const renderEmptyCharts = () => {
	if (!trendChartRef.value || !stackChartRef.value || !pieChartRef.value || !gaugeChartRef.value || !heatmapChartRef.value) return;

	const emptyGraphic = {
		type: 'text',
		left: 'center',
		top: 'middle',
		style: {
			text: '暂无实时数据',
			fill: '#94a3b8',
			fontSize: 14,
		},
	};

	ensureChart('trend', trendChartRef.value).setOption({ xAxis: { show: false }, yAxis: { show: false }, series: [], graphic: emptyGraphic }, true);
	ensureChart('stack', stackChartRef.value).setOption({ xAxis: { show: false }, yAxis: { show: false }, series: [], graphic: emptyGraphic }, true);
	ensureChart('heatmap', heatmapChartRef.value).setOption({ xAxis: { show: false }, yAxis: { show: false }, visualMap: { show: false }, series: [], graphic: emptyGraphic }, true);

	updatePieChart(ensureChart('pie', pieChartRef.value), null);
	updateGaugeChart(ensureChart('gauge', gaugeChartRef.value), null);
};

const renderCharts = () => {
	if (!trendChartRef.value || !stackChartRef.value || !pieChartRef.value || !gaugeChartRef.value || !heatmapChartRef.value) return;

	const data = recentRecords.value;
	if (!data.length) {
		renderEmptyCharts();
		return;
	}

	updateTrendChart(ensureChart('trend', trendChartRef.value), data);
	updateStackChart(ensureChart('stack', stackChartRef.value), data);
	updatePieChart(ensureChart('pie', pieChartRef.value), latestRecord.value);
	updateGaugeChart(ensureChart('gauge', gaugeChartRef.value), latestRecord.value);
	updateHeatmapChart(ensureChart('heatmap', heatmapChartRef.value), data);
};

const handleResize = () => {
	Object.values(chartInstances).forEach((chart) => chart?.resize());
};

const fetchBehaviorData = async (manual = false) => {
	if (!pageAlive || isFetching) return;
	isFetching = true;
	if (manual) isLoading.value = true;

	try {
		const res = await axios.get('/api/behavior/stats', { timeout: 4500 });
		const rows = res?.data?.code === 200 && Array.isArray(res?.data?.data) ? (res.data.data as BehaviorItem[]) : [];
		records.value = rows;
		apiOnline.value = true;
	} catch {
		apiOnline.value = false;
	} finally {
		lastUpdatedAt.value = new Date();
		if (manual) isLoading.value = false;
		isFetching = false;

		if (pageAlive) {
			nextTick(() => {
				renderCharts();
			});
		}
	}
};

const handleManualRefresh = () => {
	void fetchBehaviorData(true);
};

onMounted(async () => {
	pageAlive = true;
	window.addEventListener('resize', handleResize);
	await fetchBehaviorData(true);
	refreshTimer = setInterval(() => {
		void fetchBehaviorData(false);
	}, REFRESH_INTERVAL_MS);
});

onBeforeUnmount(() => {
	pageAlive = false;
	window.removeEventListener('resize', handleResize);
	if (refreshTimer) {
		clearInterval(refreshTimer);
		refreshTimer = null;
	}
	disposeCharts();
});
</script>

<style scoped>
.behavior-bi-page {
	min-height: calc(100vh - 150px);
	padding: 18px;
	background:
		radial-gradient(120% 110% at 4% 0%, rgba(14, 165, 233, 0.12), transparent 55%),
		radial-gradient(100% 100% at 92% 10%, rgba(22, 163, 74, 0.08), transparent 60%),
		linear-gradient(180deg, #f8fbff 0%, #f2f7ff 100%);
}

.bi-header {
	display: flex;
	align-items: flex-start;
	justify-content: space-between;
	gap: 16px;
	flex-wrap: wrap;
	margin-bottom: 16px;
}

.bi-title {
	margin: 0;
	font-size: 24px;
	font-weight: 700;
	letter-spacing: 0.01em;
	color: #0f172a;
}

.bi-subtitle {
	margin: 8px 0 0;
	color: #475569;
	font-size: 14px;
}

.bi-actions {
	display: flex;
	align-items: center;
	gap: 12px;
	flex-wrap: wrap;
}

.live-badge {
	display: inline-flex;
	align-items: center;
	gap: 6px;
	padding: 6px 10px;
	border-radius: 999px;
	background: rgba(37, 99, 235, 0.08);
	color: #1d4ed8;
	font-weight: 600;
	font-size: 13px;
}

.live-dot {
	width: 8px;
	height: 8px;
	border-radius: 50%;
	background: #16a34a;
	box-shadow: 0 0 0 0 rgba(22, 163, 74, 0.5);
	animation: pulse 1.5s infinite;
}

.live-dot.offline {
	background: #ef4444;
	box-shadow: none;
	animation: none;
}

.last-updated {
	padding: 6px 10px;
	border-radius: 10px;
	background: rgba(15, 23, 42, 0.04);
	color: #334155;
	font-size: 13px;
}

.refresh-btn {
	height: 38px;
	padding: 0 18px;
	border-radius: 12px;
	border: 1px solid #0f766e;
	background: linear-gradient(135deg, #0f766e 0%, #0d9488 100%);
	color: #ffffff !important;
	font-weight: 700;
	letter-spacing: 0.02em;
	box-shadow: 0 8px 18px rgba(13, 148, 136, 0.25);
}

.refresh-btn:hover,
.refresh-btn:focus {
	border-color: #0b6a61;
	background: linear-gradient(135deg, #0f6a63 0%, #0b7f77 100%);
	color: #ffffff !important;
}

.refresh-btn:active {
	transform: translateY(1px);
}

.refresh-btn.is-loading {
	opacity: 0.94;
}

.refresh-btn :deep(span) {
	color: #ffffff !important;
	background: none !important;
	text-shadow: none !important;
	-webkit-text-fill-color: currentColor;
}

.refresh-btn :deep(.el-icon),
.refresh-btn :deep(.circular) {
	color: #ffffff !important;
}

.kpi-grid {
	display: grid;
	grid-template-columns: repeat(5, minmax(0, 1fr));
	gap: 12px;
	margin-bottom: 16px;
}

.kpi-item {
	padding: 14px 16px;
	border-radius: 14px;
	border: 1px solid rgba(148, 163, 184, 0.2);
	background: rgba(255, 255, 255, 0.78);
	backdrop-filter: blur(2px);
}

.kpi-label {
	font-size: 13px;
	color: #64748b;
}

.kpi-value {
	margin-top: 8px;
	font-size: 26px;
	font-weight: 700;
	line-height: 1;
	color: #0f172a;
}

.charts-grid {
	display: grid;
	grid-template-columns: repeat(12, minmax(0, 1fr));
	gap: 14px;
}

.panel {
	grid-column: span 4;
	padding: 12px 14px 10px;
	border-radius: 14px;
	border: 1px solid rgba(148, 163, 184, 0.24);
	background: rgba(255, 255, 255, 0.86);
	box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
}

.panel-wide {
	grid-column: span 8;
}

.panel-full {
	grid-column: span 12;
}

.panel-compact {
	grid-column: span 4;
}

.panel-header h3 {
	margin: 0;
	font-size: 15px;
	font-weight: 600;
	color: #1e293b;
}

.panel-chart {
	height: 320px;
	margin-top: 8px;
}

.panel-chart-compact {
	height: 280px;
}

@keyframes pulse {
	0% {
		box-shadow: 0 0 0 0 rgba(22, 163, 74, 0.5);
	}
	70% {
		box-shadow: 0 0 0 6px rgba(22, 163, 74, 0);
	}
	100% {
		box-shadow: 0 0 0 0 rgba(22, 163, 74, 0);
	}
}

@media (max-width: 1300px) {
	.kpi-grid {
		grid-template-columns: repeat(3, minmax(0, 1fr));
	}

	.panel,
	.panel-wide,
	.panel-compact,
	.panel-full {
		grid-column: span 12;
	}
}

@media (max-width: 840px) {
	.behavior-bi-page {
		padding: 12px;
	}

	.kpi-grid {
		grid-template-columns: repeat(2, minmax(0, 1fr));
	}

	.bi-title {
		font-size: 20px;
	}
}

@media (max-width: 560px) {
	.kpi-grid {
		grid-template-columns: 1fr;
	}

	.panel-chart,
	.panel-chart-compact {
		height: 260px;
	}
}
</style>
