<template>
	<div class="system-predict-container layout-padding">
		<div class="system-predict-padding layout-padding-auto layout-padding-view predict-view">
			<div class="control-panel">
				<div class="control-group">
					<label class="control-label">检测类型</label>
					<el-select v-model="kind" placeholder="请选择检测类型" size="large" @change="getData" class="control-select">
						<el-option v-for="item in state.kind_items" :key="item.value" :label="item.label" :value="item.value" />
					</el-select>
				</div>

				<div class="control-group">
					<label class="control-label">模型选择</label>
					<el-select v-model="weight" placeholder="请选择模型" size="large" @change="onWeightChange" class="control-select">
						<el-option v-for="item in state.weight_items" :key="item.value" :label="item.label" :value="item.value" />
					</el-select>
				</div>

				<div class="control-group">
					<label class="control-label">置信度阈值</label>
					<div class="slider-wrapper">
						<el-slider v-model="conf" :format-tooltip="formatTooltip" class="control-slider" />
						<span class="slider-value">{{ (conf / 100).toFixed(2) }}</span>
					</div>
				</div>

				<el-button type="primary" @click="upData" :loading="isLoading" class="predict-button">开始预测</el-button>
			</div>

			<div class="content-area" :class="{ 'single-pane': !state.predictionResult.summary }">
				<div class="upload-section">
					<el-card shadow="never" class="upload-card">
						<el-upload
							v-model="state.img"
							ref="uploadFile"
							class="avatar-uploader"
							action="http://localhost:9999/files/upload"
							:show-file-list="false"
							:on-success="handleAvatarSuccess"
						>
							<div class="upload-content">
								<img v-if="imageUrl" :src="imageUrl" class="preview-image" />
								<div v-else class="upload-placeholder">
									<el-icon class="upload-icon">
										<Plus />
									</el-icon>
									<p class="upload-text">点击上传图片进行预测</p>
									<p class="upload-hint">支持 JPG、PNG</p>
								</div>
							</div>
						</el-upload>
					</el-card>
				</div>

				<div class="result-section" v-if="state.predictionResult.summary">
					<el-card class="result-card" shadow="never">
						<template #header>
							<div class="result-header">预测结果</div>
						</template>
						<div class="result-content">
							<div class="metric-grid">
								<div class="metric-item">
									<span class="metric-label">目标总数</span>
									<strong class="metric-value">{{ state.predictionResult.total }}</strong>
								</div>
								<div class="metric-item">
									<span class="metric-label">平均置信度</span>
									<strong class="metric-value">{{ state.predictionResult.confidence }}</strong>
								</div>
								<div class="metric-item">
									<span class="metric-label">处理耗时</span>
									<strong class="metric-value">{{ state.predictionResult.allTime }}</strong>
								</div>
							</div>

							<div class="result-item">
								<span class="result-label">识别摘要</span>
								<span class="result-value">{{ state.predictionResult.summary }}</span>
							</div>

							<div class="confidence-bar">
								<div class="confidence-fill" :style="{ width: confidenceWidth }"></div>
								<span class="confidence-text">平均置信度 {{ state.predictionResult.confidence }}</span>
							</div>

							<div class="chart-group">
								<div class="chart-card">
									<div class="chart-title">类别数量分布</div>
									<div ref="countChartRef" class="chart-view"></div>
								</div>
								<div class="chart-card">
									<div class="chart-title">目标置信度分布</div>
									<div ref="confidenceChartRef" class="chart-view"></div>
								</div>
							</div>
						</div>
					</el-card>
				</div>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts" name="imgPredict">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue';
import type { UploadInstance, UploadProps } from 'element-plus';
import { ElMessage } from 'element-plus';
import request from '/@/utils/request';
import { Plus } from '@element-plus/icons-vue';
import { useUserInfo } from '/@/stores/userInfo';
import { storeToRefs } from 'pinia';
import { formatDate } from '/@/utils/formatTime';
import * as echarts from 'echarts';

type DetectionItem = {
	label: string;
	confidence: number;
};

type ClassStat = {
	label: string;
	count: number;
};

const imageUrl = ref('');
const conf = ref(50);
const weight = ref('');
const kind = ref('');
const uploadFile = ref<UploadInstance>();
const isLoading = ref(false);
const stores = useUserInfo();
const { userInfos } = storeToRefs(stores);

const countChartRef = ref<HTMLElement | null>(null);
const confidenceChartRef = ref<HTMLElement | null>(null);
let countChart: echarts.ECharts | null = null;
let confidenceChart: echarts.ECharts | null = null;

const labelAlias: Record<string, string> = {
	head: '人数',
	head_down: '低头',
	phone: '看手机',
	sleep: '睡觉',
	sleeping: '睡觉',
};

const mapLabel = (label: string) => labelAlias[label] || label;
const isSuccessCode = (code: unknown) => String(code) === '0' || Number(code) === 0;

const state = reactive({
	weight_items: [] as any[],
	kind_items: [
		{ value: 'corn', label: '玉米' },
		{ value: 'rice', label: '水稻' },
		{ value: 'strawberry', label: '草莓' },
		{ value: 'tomato', label: '西红柿' },
		{ value: 'head', label: '人数' },
	],
	img: '',
	predictionResult: {
		summary: '',
		total: 0,
		confidence: '--',
		allTime: '--',
		classStats: [] as ClassStat[],
		detections: [] as DetectionItem[],
	},
	form: {
		username: '',
		inputImg: null as any,
		weight: '',
		conf: null as any,
		kind: '',
		startTime: '',
	},
});

const confidenceWidth = computed(() => {
	const raw = String(state.predictionResult.confidence || '0').replace('%', '');
	const num = Number(raw);
	if (Number.isNaN(num)) return '0%';
	return `${Math.max(0, Math.min(100, num))}%`;
});

const formatTooltip = (val: number) => val / 100;

const parseMaybeJson = <T = any>(value: any, fallback: T): T => {
	if (value === null || value === undefined) return fallback;
	if (typeof value !== 'string') return value as T;
	const txt = value.trim();
	if (!txt || txt === 'null' || txt === 'undefined') return fallback;
	try {
		return JSON.parse(txt) as T;
	} catch {
		return fallback;
	}
};

const toConfPercent = (value: unknown) => {
	const n = Number(value);
	if (Number.isNaN(n)) return 0;
	if (n <= 1) return n * 100;
	return n;
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

const handleAvatarSuccess: UploadProps['onSuccess'] = (response, currentUploadFile) => {
	imageUrl.value = URL.createObjectURL(currentUploadFile.raw!);
	state.img = response?.data || '';
};

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
					return (keywordsByKind[name] || [name]).some((kw) => value.includes(kw));
			  });
		state.weight_items = filtered.length ? filtered : sourceWeightItems;
		const current = String(weight.value || '').toLowerCase();
		const exists = state.weight_items.some((it: any) => String(it.value || '').toLowerCase() === current);
		if (!exists) weight.value = state.weight_items.length ? state.weight_items[0].value : '';
		if (!name) {
			const selectedWeight = String(weight.value || '');
			if (selectedWeight && !kind.value) {
				const inferred = inferKindFromWeight(selectedWeight);
				if (inferred) kind.value = inferred;
			}
		}
	});
};

const onWeightChange = () => {
	const inferred = inferKindFromWeight(String(weight.value || ''));
	if (inferred) kind.value = inferred;
};

const updateCharts = () => {
	if (!countChartRef.value || !confidenceChartRef.value) return;
	if (!countChart) countChart = echarts.init(countChartRef.value);
	if (!confidenceChart) confidenceChart = echarts.init(confidenceChartRef.value);

	const classStats = state.predictionResult.classStats;
	const detections = state.predictionResult.detections;

	countChart.setOption({
		tooltip: { trigger: 'axis' },
		xAxis: {
			type: 'category',
			data: classStats.map((item) => mapLabel(item.label)),
			axisLabel: { color: '#4f647a' },
		},
		yAxis: { type: 'value', minInterval: 1, axisLabel: { color: '#4f647a' } },
		grid: { left: 40, right: 18, top: 18, bottom: 40 },
		series: [
			{
				type: 'bar',
				data: classStats.map((item) => item.count),
				barWidth: 22,
				itemStyle: { color: '#2f80ed', borderRadius: [6, 6, 0, 0] },
			},
		],
	});

	const confData = detections.map((item, index) => ({
		name: `${mapLabel(item.label)} ${index + 1}`,
		value: Number(toConfPercent(item.confidence).toFixed(2)),
	}));
	confidenceChart.setOption({
		tooltip: { trigger: 'axis' },
		xAxis: {
			type: 'category',
			data: confData.map((item) => item.name),
			axisLabel: { show: false },
		},
		yAxis: {
			type: 'value',
			min: 0,
			max: 100,
			axisLabel: { formatter: '{value}%', color: '#4f647a' },
		},
		grid: { left: 44, right: 16, top: 18, bottom: 28 },
		series: [
			{
				name: '置信度',
				type: 'line',
				smooth: true,
				data: confData.map((item) => item.value),
				lineStyle: { color: '#24b3a6', width: 2 },
				itemStyle: { color: '#24b3a6' },
				areaStyle: { color: 'rgba(36, 179, 166, 0.12)' },
			},
		],
	});
};

const applyPredictionPayload = (payload: any) => {
	const objectsRaw = Array.isArray(payload?.objects)
		? payload.objects
		: Array.isArray(payload?.detections)
			? payload.detections
			: [];

	const detections: DetectionItem[] = objectsRaw
		.map((item: any) => {
			const label = String(item?.label || item?.name || '').trim();
			const confidence = Number(item?.confidence ?? item?.score ?? 0);
			return {
				label,
				confidence: Number.isNaN(confidence) ? 0 : confidence,
			};
		})
		.filter((item: DetectionItem) => Boolean(item.label));

	const countsMap: Record<string, number> = {};
	if (payload?.counts && typeof payload.counts === 'object') {
		Object.entries(payload.counts).forEach(([key, value]) => {
			const n = Number(value);
			if (!Number.isNaN(n)) countsMap[String(key)] = n;
		});
	}
	if (!Object.keys(countsMap).length) {
		detections.forEach((item) => {
			countsMap[item.label] = (countsMap[item.label] || 0) + 1;
		});
	}

	const classStats: ClassStat[] = Object.entries(countsMap)
		.map(([label, count]) => ({ label, count: Number(count) }))
		.sort((a, b) => b.count - a.count);

	const total = classStats.reduce((sum, item) => sum + item.count, 0);
	const avgConfidence = detections.length
		? detections.reduce((sum, item) => sum + toConfPercent(item.confidence), 0) / detections.length
		: Number(String(payload?.confidence || '').replace('%', '')) || 0;

	const onlyHead = classStats.length === 1 && classStats[0].label.toLowerCase() === 'head';
	let summary = '未检测到目标';
	if (total > 0) {
		if (onlyHead) {
			summary = `检测到人数 ${total} 人`;
		} else {
			const top = classStats
				.slice(0, 3)
				.map((item) => `${mapLabel(item.label)} ${item.count}`)
				.join('，');
			summary = `共检测到 ${total} 个目标，主要类别：${top}`;
		}
	}

	state.predictionResult.summary = summary;
	state.predictionResult.total = total;
	state.predictionResult.confidence = `${Math.max(0, Math.min(100, avgConfidence)).toFixed(2)}%`;
	state.predictionResult.allTime = String(payload?.allTime || '--');
	state.predictionResult.classStats = classStats;
	state.predictionResult.detections = detections;

	if (payload?.outImg) imageUrl.value = payload.outImg;
	nextTick(() => updateCharts());
};

const upData = () => {
	if (!state.img) {
		ElMessage.warning('请先上传图片');
		return;
	}
	state.form.weight = weight.value;
	state.form.conf = conf.value / 100;
	state.form.username = userInfos.value.userName;
	state.form.inputImg = state.img;
	state.form.kind = kind.value;
	state.form.startTime = formatDate(new Date(), 'YYYY-mm-dd HH:MM:SS');
	isLoading.value = true;

	request
		.post('/api/flask/predict', state.form)
		.then((res) => {
			if (!isSuccessCode(res?.code)) {
				ElMessage.error(res?.msg || '预测失败');
				return;
			}
			const payload = parseMaybeJson<any>(res?.data, res?.data || {});
			applyPredictionPayload(payload);
			ElMessage.success('预测成功');
		})
		.catch((e) => ElMessage.error(String(e)))
		.finally(() => {
			isLoading.value = false;
		});
};

const handleResize = () => {
	countChart?.resize();
	confidenceChart?.resize();
};

onMounted(() => {
	getData();
	window.addEventListener('resize', handleResize);
});

onBeforeUnmount(() => {
	window.removeEventListener('resize', handleResize);
	countChart?.dispose();
	confidenceChart?.dispose();
	countChart = null;
	confidenceChart = null;
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
	padding-bottom: 30px;
	box-sizing: border-box;
	display: flex;
	flex-direction: column;
	gap: 20px;
	overflow: auto !important;
	border-radius: 18px;
	border: 1px solid #dbe4ea;
	background: #fff;
	box-shadow: 0 8px 28px rgba(15, 23, 42, 0.06);
}

.control-panel {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)) auto;
	gap: 14px;
	align-items: end;
	padding: 18px;
	border-radius: 14px;
	border: 1px solid #e1e8ee;
	background: #f8fbfd;
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

.slider-wrapper {
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

.predict-button {
	height: 42px;
	min-width: 140px;
	font-weight: 600;
	letter-spacing: 0.02em;
}

.content-area {
	display: grid;
	grid-template-columns: 1fr 1fr;
	gap: 20px;
	align-items: start;
}

.content-area.single-pane {
	grid-template-columns: 1fr;
}

.upload-section,
.result-section {
	min-height: 440px;
}

.upload-card,
.result-card {
	height: 100%;
	border-radius: 14px;
	border: 1px solid #dde5ec;
	background: #fff;
}

.upload-card :deep(.el-card__body) {
	height: 100%;
	padding: 14px;
	box-sizing: border-box;
}

.result-card :deep(.el-card__body) {
	padding: 14px;
	box-sizing: border-box;
}

.avatar-uploader {
	width: 100%;
	height: 100%;
}

.avatar-uploader :deep(.el-upload) {
	width: 100%;
	height: 100%;
}

.upload-content {
	width: 100%;
	height: 100%;
	min-height: 390px;
	display: flex;
	align-items: center;
	justify-content: center;
	border-radius: 12px;
	border: 1px dashed #b9cad7;
	background: linear-gradient(180deg, #f7fafc 0%, #f2f7fb 100%);
	padding: 14px;
	box-sizing: border-box;
	cursor: pointer;
	transition: border-color 0.2s ease, background 0.2s ease;
}

.upload-content:hover {
	border-color: #8eabc2;
	background: linear-gradient(180deg, #f6fafd 0%, #edf4f9 100%);
}

.preview-image {
	max-width: 100%;
	max-height: 100%;
	object-fit: contain;
	border-radius: 8px;
}

.upload-placeholder {
	display: flex;
	flex-direction: column;
	align-items: center;
	text-align: center;
	gap: 10px;
	color: #2f4f6f;
}

.upload-icon {
	font-size: 48px;
	opacity: 0.75;
}

.upload-text {
	margin: 0;
	font-size: 17px;
	font-weight: 700;
}

.upload-hint {
	margin: 0;
	font-size: 13px;
	color: #62788f;
}

.result-card :deep(.el-card__header) {
	padding: 14px 16px;
	border-bottom: 1px solid #e3eaf0;
	background: #f7fafc;
}

.result-header {
	font-size: 15px;
	font-weight: 700;
	color: #1f364f;
}

.result-content {
	display: flex;
	flex-direction: column;
	gap: 14px;
}

.metric-grid {
	display: grid;
	grid-template-columns: repeat(3, minmax(0, 1fr));
	gap: 10px;
}

.metric-item {
	padding: 12px;
	border: 1px solid #e4edf4;
	border-radius: 10px;
	background: #fbfdff;
	display: flex;
	flex-direction: column;
	gap: 6px;
}

.metric-label {
	font-size: 12px;
	color: #62798f;
}

.metric-value {
	font-size: 18px;
	font-weight: 700;
	color: #173754;
}

.result-item {
	display: flex;
	flex-direction: column;
	gap: 8px;
	padding: 12px;
	border: 1px solid #e6edf3;
	border-radius: 10px;
	background: #fbfdff;
}

.result-label {
	font-size: 12px;
	font-weight: 600;
	color: #597087;
	text-transform: uppercase;
	letter-spacing: 0.05em;
}

.result-value {
	font-size: 15px;
	font-weight: 700;
	color: #15324e;
	word-break: break-word;
}

.confidence-bar {
	position: relative;
	height: 32px;
	border-radius: 999px;
	border: 1px solid #d6e1ea;
	background: #eef3f8;
	overflow: hidden;
	display: flex;
	align-items: center;
}

.confidence-fill {
	position: absolute;
	left: 0;
	top: 0;
	height: 100%;
	background: linear-gradient(90deg, #2f80ed 0%, #24b3a6 100%);
	transition: width 0.25s ease;
}

.confidence-text {
	position: relative;
	z-index: 1;
	width: 100%;
	text-align: center;
	font-size: 13px;
	font-weight: 700;
	color: #1f3c5b;
}

.chart-group {
	display: grid;
	grid-template-columns: 1fr;
	gap: 12px;
}

.chart-card {
	border: 1px solid #e3ebf2;
	border-radius: 10px;
	padding: 10px;
	background: #fcfeff;
}

.chart-title {
	font-size: 13px;
	font-weight: 600;
	color: #37526c;
	margin-bottom: 6px;
}

.chart-view {
	height: 210px;
	width: 100%;
}

@media (max-width: 1024px) {
	.control-panel {
		grid-template-columns: 1fr 1fr;
	}

	.content-area {
		grid-template-columns: 1fr;
	}
}

@media (max-width: 768px) {
	.system-predict-container {
		padding: 12px;
	}

	.predict-view {
		padding: 14px;
		gap: 14px;
		border-radius: 12px;
	}

	.control-panel {
		grid-template-columns: 1fr;
		padding: 14px;
	}

	.predict-button {
		width: 100%;
	}

	.metric-grid {
		grid-template-columns: 1fr;
	}

	.upload-section,
	.result-section {
		min-height: 320px;
	}

	.upload-content {
		min-height: 300px;
	}

	.chart-view {
		height: 180px;
	}
}
</style>