<template>
	<div class="system-predict-container layout-padding">
		<div class="system-predict-padding layout-padding-auto layout-padding-view predict-view">
			<section class="control-panel">
				<div class="control-grid">
					<div class="control-group">
						<label class="control-label">检测类型</label>
						<el-select v-model="kind" placeholder="请选择检测类型" size="large" class="control-select" @change="getData">
							<el-option v-for="item in state.kind_items" :key="item.value" :label="item.label" :value="item.value" />
						</el-select>
					</div>

					<div class="control-group">
						<label class="control-label">模型选择</label>
						<el-select v-model="weight" placeholder="请选择模型" size="large" class="control-select" @change="onWeightChange">
							<el-option v-for="item in state.weight_items" :key="item.value" :label="item.label" :value="item.value" />
						</el-select>
					</div>

					<div class="control-group slider-group">
						<label class="control-label">置信度阈值</label>
						<div class="slider-row">
							<el-slider v-model="conf" :format-tooltip="formatTooltip" class="control-slider" />
							<span class="slider-value">{{ (conf / 100).toFixed(2) }}</span>
						</div>
					</div>
				</div>

				<div class="action-row">
					<el-button type="primary" :loading="state.processing" class="action-btn" @click="start">开始录制</el-button>
					<el-button type="danger" plain class="action-btn" @click="stop">结束录制</el-button>
				</div>

				<p class="upload-tip">{{ state.cameraIsShow ? '摄像检测进行中，可随时结束录制' : '点击开始录制后将实时显示检测画面' }}</p>
			</section>

			<section v-if="state.isShow" class="progress-panel">
				<div class="progress-head">
					<span class="progress-title">处理进度</span>
					<span class="progress-value">{{ state.percentage }}%</span>
				</div>
				<el-progress :stroke-width="18" :percentage="state.percentage" />
			</section>

			<section class="workspace-grid">
				<section class="preview-panel">
					<div class="panel-head">
						<h3>摄像检测画面</h3>
						<span>实时流展示</span>
					</div>
					<div class="media-stage">
						<img v-if="state.cameraIsShow" class="video-frame" :src="state.video_path" />
						<div v-else class="empty-state">
							<el-icon class="empty-icon"><VideoCamera /></el-icon>
							<p>尚未开始摄像检测</p>
						</div>
					</div>
				</section>

				<section class="chart-panel">
					<div class="panel-head">
						<h3>实时识别统计</h3>
						<span>每秒更新</span>
					</div>
					<div class="metric-grid">
						<div class="metric-item">
							<span class="metric-label">当前帧</span>
							<strong class="metric-value">{{ state.latest.frame }}</strong>
						</div>
						<div class="metric-item">
							<span class="metric-label">目标数</span>
							<strong class="metric-value">{{ state.latest.total }}</strong>
						</div>
						<div class="metric-item">
							<span class="metric-label">平均置信度</span>
							<strong class="metric-value">{{ state.latest.avgConfidence.toFixed(2) }}%</strong>
						</div>
					</div>
					<div class="chart-box">
						<div class="chart-title">目标数量与置信度趋势</div>
						<div ref="trendChartRef" class="chart-view"></div>
					</div>
					<div class="chart-box">
						<div class="chart-title">当前帧类别分布</div>
						<div ref="classChartRef" class="chart-view small"></div>
					</div>
				</section>
			</section>
		</div>
	</div>
</template>

<script setup lang="ts" name="cameraPredict">
import { nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import request from '/@/utils/request';
import { useUserInfo } from '/@/stores/userInfo';
import { storeToRefs } from 'pinia';
import { SocketService } from '/@/utils/socket';
import { formatDate } from '/@/utils/formatTime';
import { VideoCamera } from '@element-plus/icons-vue';
import * as echarts from 'echarts';

const stores = useUserInfo();
const conf = ref(50);
const kind = ref('');
const weight = ref('');
const flaskBaseUrl = import.meta.env.VITE_FLASK_BASE_URL || 'http://127.0.0.1:5000';
const { userInfos } = storeToRefs(stores);

const trendChartRef = ref<HTMLElement | null>(null);
const classChartRef = ref<HTMLElement | null>(null);
let trendChart: echarts.ECharts | null = null;
let classChart: echarts.ECharts | null = null;

const currentTaskId = ref('');
const frameSeries = ref<number[]>([]);
const totalSeries = ref<number[]>([]);
const confSeries = ref<number[]>([]);
const currentCounts = ref<Record<string, number>>({});

const labelAlias: Record<string, string> = {
	head: '人数',
	head_down: '低头',
	phone: '看手机',
	sleep: '睡觉',
	sleeping: '睡觉',
};

const state = reactive({
	weight_items: [] as any[],
	kind_items: [
		{ value: 'corn', label: '玉米' },
		{ value: 'rice', label: '水稻' },
		{ value: 'strawberry', label: '草莓' },
		{ value: 'tomato', label: '西红柿' },
		{ value: 'head', label: '人数' },
	],
	video_path: '',
	percentage: 0,
	isShow: false,
	cameraIsShow: false,
	processing: false,
	latest: {
		frame: 0,
		total: 0,
		avgConfidence: 0,
	},
	form: {
		username: '',
		weight: '',
		conf: null as any,
		kind: '',
		startTime: '',
		taskId: '',
	},
});

const mapLabel = (label: string) => labelAlias[label] || label;
const isSuccessCode = (code: unknown) => String(code) === '0' || Number(code) === 0;
const formatTooltip = (val: number) => val / 100;
const socketService = new SocketService();

const parseMaybeJson = <T = any>(value: any, fallback: T): T => {
	if (value === null || value === undefined) return fallback;
	if (typeof value !== 'string') return value as T;
	const normalized = value.trim();
	if (!normalized || normalized === 'undefined' || normalized === 'null') return fallback;
	try {
		return JSON.parse(normalized) as T;
	} catch {
		return fallback;
	}
};

const unwrapSocketPayload = (payload: any) => {
	if (payload && typeof payload === 'object' && 'data' in payload) return payload.data;
	return payload;
};

const isCurrentTaskOrLegacy = (taskId: unknown) => {
	if (taskId !== undefined && taskId !== null && String(taskId).trim() !== '') {
		if (!currentTaskId.value) return false;
		return String(taskId) === currentTaskId.value;
	}
	return state.processing;
};

const extractWeightItems = (raw: any) => {
	const payload = parseMaybeJson<any>(raw, raw);
	if (Array.isArray(payload?.weight_items)) return payload.weight_items;
	if (Array.isArray(payload?.data?.weight_items)) return payload.data.weight_items;
	if (typeof payload?.data === 'string') {
		const parsed = parseMaybeJson<any>(payload.data, {});
		if (Array.isArray(parsed?.weight_items)) return parsed.weight_items;
	}
	return [];
};

const inferKindFromWeight = (w: string) => {
	if (!w) return '';
	const s = w.toLowerCase();
	if (s.includes('tomato')) return 'tomato';
	if (s.includes('strawberry')) return 'strawberry';
	if (s.includes('corn') || s.includes('maize')) return 'corn';
	if (s.includes('rice') || s.includes('paddy')) return 'rice';
	if (s.includes('head') || s.includes('count')) return 'head';
	return '';
};

const disposeCharts = () => {
	trendChart?.dispose();
	classChart?.dispose();
	trendChart = null;
	classChart = null;
};

const resetLiveStats = () => {
	frameSeries.value = [];
	totalSeries.value = [];
	confSeries.value = [];
	currentCounts.value = {};
	state.latest.frame = 0;
	state.latest.total = 0;
	state.latest.avgConfidence = 0;
	state.percentage = 0;
};

const updateCharts = () => {
	if (!trendChartRef.value || !classChartRef.value) return;
	if (!trendChart) trendChart = echarts.init(trendChartRef.value);
	if (!classChart) classChart = echarts.init(classChartRef.value);

	trendChart.setOption({
		tooltip: { trigger: 'axis' },
		legend: { data: ['目标数', '平均置信度'] },
		grid: { left: 40, right: 16, top: 30, bottom: 30 },
		xAxis: { type: 'category', data: frameSeries.value, axisLabel: { color: '#4f647a' } },
		yAxis: [
			{ type: 'value', name: '目标数', minInterval: 1, axisLabel: { color: '#4f647a' } },
			{ type: 'value', name: '置信度', min: 0, max: 100, axisLabel: { formatter: '{value}%', color: '#4f647a' } },
		],
		series: [
			{
				name: '目标数',
				type: 'line',
				smooth: true,
				data: totalSeries.value,
				lineStyle: { color: '#2f80ed', width: 2 },
				itemStyle: { color: '#2f80ed' },
			},
			{
				name: '平均置信度',
				type: 'line',
				smooth: true,
				yAxisIndex: 1,
				data: confSeries.value,
				lineStyle: { color: '#24b3a6', width: 2 },
				itemStyle: { color: '#24b3a6' },
				areaStyle: { color: 'rgba(36, 179, 166, 0.12)' },
			},
		],
	});

	const classEntries = Object.entries(currentCounts.value).sort((a, b) => b[1] - a[1]);
	classChart.setOption({
		tooltip: { trigger: 'axis' },
		grid: { left: 42, right: 16, top: 18, bottom: 32 },
		xAxis: {
			type: 'category',
			data: classEntries.map(([label]) => mapLabel(label)),
			axisLabel: { color: '#4f647a' },
		},
		yAxis: { type: 'value', minInterval: 1, axisLabel: { color: '#4f647a' } },
		series: [
			{
				type: 'bar',
				barWidth: 22,
				data: classEntries.map(([, count]) => count),
				itemStyle: { color: '#22a6b3', borderRadius: [6, 6, 0, 0] },
			},
		],
	});
};

const handleResize = () => {
	trendChart?.resize();
	classChart?.resize();
};

socketService.on('message', (payload: any) => {
	const incoming = unwrapSocketPayload(payload);
	if (typeof incoming === 'string') {
		if (/^connected to websocket server!?$/i.test(incoming.trim())) return;
		return;
	}
	if (!isCurrentTaskOrLegacy(incoming?.taskId)) return;
	const text = String(incoming?.text || '').trim();
	if (!text) return;
	if (incoming?.type === 'success') {
		ElMessage.success(text);
	} else if (incoming?.type === 'error') {
		ElMessage.error(text);
	}
});

socketService.on('progress', (payload: any) => {
	const incoming = unwrapSocketPayload(payload);
	if (typeof incoming === 'object' && incoming !== null) {
		if (!isCurrentTaskOrLegacy(incoming.taskId)) return;
	}
	const progress = Number(
		typeof incoming === 'object' && incoming !== null ? incoming.progress ?? incoming.value ?? incoming.percentage : incoming
	);
	if (Number.isNaN(progress)) return;
	state.percentage = Math.max(0, Math.min(100, Math.round(progress)));
	state.isShow = true;
	if (state.percentage >= 100) {
		state.processing = false;
		setTimeout(() => {
			state.isShow = false;
		}, 1500);
	}
});

socketService.on('stats', (payload: any) => {
	const incoming = unwrapSocketPayload(payload);
	if (!incoming || typeof incoming !== 'object') return;
	if (!isCurrentTaskOrLegacy(incoming.taskId)) return;
	const frame = Number(incoming.frame || frameSeries.value.length + 1);
	const total = Number(incoming.total || 0);
	const avgConfidence = Number(incoming.avgConfidence || 0);
	if (!Number.isFinite(frame) || !Number.isFinite(total) || !Number.isFinite(avgConfidence)) return;

	frameSeries.value.push(frame);
	totalSeries.value.push(total);
	confSeries.value.push(avgConfidence);
	if (frameSeries.value.length > 50) {
		frameSeries.value.shift();
		totalSeries.value.shift();
		confSeries.value.shift();
	}
	currentCounts.value = incoming.counts && typeof incoming.counts === 'object' ? incoming.counts : {};
	state.latest.frame = frame;
	state.latest.total = total;
	state.latest.avgConfidence = avgConfidence;
	updateCharts();
});

const getData = () => {
	request.get('/api/flask/file_names').then((res) => {
		if (!isSuccessCode(res?.code)) {
			ElMessage.error(res?.msg || '模型列表加载失败');
			return;
		}
		const sourceWeightItems = extractWeightItems(res?.data);
		const name = String(kind.value || '').toLowerCase();
		const keywordsByKind: Record<string, string[]> = {
			corn: ['corn', 'maize'],
			rice: ['rice', 'paddy'],
			strawberry: ['strawberry'],
			tomato: ['tomato'],
			head: ['head', 'count', 'counts'],
		};
		const filtered = !name
			? sourceWeightItems
			: sourceWeightItems.filter((item: any) => {
					const value = String(item?.value || '').toLowerCase();
					return (keywordsByKind[name] || [name]).some((keyword) => value.includes(keyword));
			  });
		state.weight_items = filtered.length ? filtered : sourceWeightItems;
		const current = String(weight.value || '').toLowerCase();
		const exists = state.weight_items.some((it: any) => String(it.value || '').toLowerCase() === current);
		if (!exists) {
			weight.value = state.weight_items.length ? state.weight_items[0].value : '';
		}
		if (!name) {
			const inferred = inferKindFromWeight(String(weight.value || ''));
			if (inferred && !kind.value) kind.value = inferred;
		}
	});
};

const onWeightChange = () => {
	const inferred = inferKindFromWeight(String(weight.value || ''));
	if (inferred) kind.value = inferred;
};

const start = () => {
	if (!weight.value || !kind.value) {
		ElMessage.warning('请先选择检测类型与模型');
		return;
	}
	currentTaskId.value = `${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
	state.form.weight = weight.value;
	state.form.kind = kind.value;
	state.form.conf = conf.value / 100;
	state.form.username = userInfos.value.userName;
	state.form.startTime = formatDate(new Date(), 'YYYY-mm-dd HH:MM:SS');
	state.form.taskId = currentTaskId.value;
	state.processing = true;
	state.cameraIsShow = true;
	state.isShow = true;
	resetLiveStats();
	nextTick(() => updateCharts());
	const queryParams = new URLSearchParams({
		username: state.form.username,
		weight: state.form.weight,
		conf: String(state.form.conf ?? ''),
		kind: state.form.kind,
		startTime: state.form.startTime,
		taskId: state.form.taskId,
	}).toString();
	state.video_path = `${flaskBaseUrl}/predictCamera?${queryParams}`;
	ElMessage.success('摄像检测已开始');
};

const stop = () => {
	if (!state.cameraIsShow) {
		ElMessage.info('当前没有正在运行的摄像检测');
		return;
	}
	state.cameraIsShow = false;
	state.processing = false;
	request
		.get('/flask/stopCamera')
		.then((res) => {
			const payload = parseMaybeJson<any>(res, res || {});
			const codeCandidate = payload?.code ?? payload?.status;
			const ok =
				isSuccessCode(codeCandidate) ||
				String(codeCandidate) === '200' ||
				Number(codeCandidate) === 200;
			if (!ok) {
				ElMessage.error(payload?.msg || payload?.message || '停止失败');
				return;
			}
			ElMessage.success('已结束摄像检测');
		})
		.catch((e) => {
			ElMessage.error(String(e));
		});
};

onMounted(() => {
	getData();
	nextTick(() => updateCharts());
	window.addEventListener('resize', handleResize);
});

onBeforeUnmount(() => {
	window.removeEventListener('resize', handleResize);
	disposeCharts();
	socketService.disconnect();
});
</script>

<style scoped lang="scss">
.system-predict-container {
	width: 100%;
	height: 100%;
	padding: 20px;
	box-sizing: border-box;
	background: #f3f6f8;
}

.predict-view {
	width: 100%;
	max-width: 1320px;
	height: 100%;
	margin: 0 auto;
	padding: 24px;
	box-sizing: border-box;
	display: flex;
	flex-direction: column;
	gap: 16px;
	overflow: auto !important;
	border-radius: 18px;
	border: 1px solid #dbe4ea;
	background: #fff;
	box-shadow: 0 8px 28px rgba(15, 23, 42, 0.06);
}

.control-panel {
	padding: 18px;
	border-radius: 14px;
	border: 1px solid #e1e8ee;
	background: #f8fbfd;
}

.control-grid {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
	gap: 14px;
	align-items: end;
}

.control-group {
	display: flex;
	flex-direction: column;
	gap: 8px;
}

.control-label {
	font-size: 13px;
	font-weight: 600;
	color: #2f3f4f;
}

.control-select {
	width: 100%;
}

.slider-row {
	display: flex;
	align-items: center;
	gap: 10px;
}

.control-slider {
	flex: 1;
	min-width: 140px;
}

.slider-value {
	min-width: 54px;
	text-align: center;
	font-weight: 700;
	font-size: 13px;
	color: #0f766e;
	padding: 6px 10px;
	border-radius: 999px;
	background: #e8f3f2;
}

.action-row {
	display: flex;
	flex-wrap: wrap;
	gap: 12px;
	margin-top: 14px;
}

.action-btn {
	height: 42px;
	padding: 0 22px;
	font-weight: 600;
	letter-spacing: 0.02em;
}

.upload-tip {
	margin: 12px 0 0;
	font-size: 13px;
	color: #587086;
}

.progress-panel {
	display: flex;
	flex-direction: column;
	gap: 10px;
	padding: 14px 16px;
	border: 1px solid #dbe6ee;
	border-radius: 12px;
	background: #fbfdff;
}

.progress-head {
	display: flex;
	justify-content: space-between;
	align-items: center;
}

.progress-title {
	font-size: 13px;
	font-weight: 600;
	color: #40576e;
}

.progress-value {
	font-size: 13px;
	font-weight: 700;
	color: #1f4a6f;
}

.workspace-grid {
	display: grid;
	grid-template-columns: 1.2fr 1fr;
	gap: 16px;
	flex: 1;
	min-height: 420px;
}

.preview-panel,
.chart-panel {
	display: flex;
	flex-direction: column;
	gap: 12px;
	min-height: 360px;
	padding: 16px;
	border-radius: 14px;
	border: 1px solid #dce6ee;
	background: #ffffff;
}

.panel-head {
	display: flex;
	justify-content: space-between;
	align-items: baseline;
	gap: 12px;
	padding-bottom: 8px;
	border-bottom: 1px solid #e8eef3;
}

.panel-head h3 {
	margin: 0;
	font-size: 16px;
	font-weight: 700;
	color: #1f364f;
}

.panel-head span {
	font-size: 12px;
	color: #667d92;
}

.media-stage {
	flex: 1;
	min-height: 300px;
	display: flex;
	align-items: center;
	justify-content: center;
	border: 1px dashed #bfd0de;
	border-radius: 12px;
	background: linear-gradient(180deg, #f7fafc 0%, #f2f7fb 100%);
	padding: 12px;
	box-sizing: border-box;
	overflow: hidden;
}

.video-frame {
	max-width: 100%;
	max-height: 100%;
	object-fit: contain;
	border-radius: 8px;
	background: #f3f7fb;
}

.empty-state {
	display: flex;
	flex-direction: column;
	align-items: center;
	gap: 10px;
	color: #57728a;
	text-align: center;
}

.empty-icon {
	font-size: 44px;
	opacity: 0.7;
}

.empty-state p {
	margin: 0;
	font-size: 14px;
}

.metric-grid {
	display: grid;
	grid-template-columns: repeat(3, minmax(0, 1fr));
	gap: 10px;
}

.metric-item {
	padding: 10px;
	border: 1px solid #e3ebf2;
	border-radius: 10px;
	background: #fbfdff;
	display: flex;
	flex-direction: column;
	gap: 4px;
}

.metric-label {
	font-size: 12px;
	color: #60778f;
}

.metric-value {
	font-size: 17px;
	font-weight: 700;
	color: #173754;
}

.chart-box {
	border: 1px solid #e3ebf2;
	border-radius: 10px;
	padding: 10px;
	background: #fcfeff;
}

.chart-title {
	font-size: 13px;
	font-weight: 600;
	color: #37526c;
	margin-bottom: 4px;
}

.chart-view {
	height: 190px;
	width: 100%;
}

.chart-view.small {
	height: 150px;
}

@media (max-width: 1024px) {
	.workspace-grid {
		grid-template-columns: 1fr;
	}
}

@media (max-width: 768px) {
	.system-predict-container {
		padding: 12px;
	}

	.predict-view {
		padding: 14px;
		gap: 12px;
		border-radius: 12px;
	}

	.control-panel {
		padding: 14px;
	}

	.action-row {
		flex-direction: column;
	}

	.action-btn {
		width: 100%;
	}

	.metric-grid {
		grid-template-columns: 1fr;
	}

	.chart-view {
		height: 170px;
	}

	.chart-view.small {
		height: 140px;
	}
}
</style>
