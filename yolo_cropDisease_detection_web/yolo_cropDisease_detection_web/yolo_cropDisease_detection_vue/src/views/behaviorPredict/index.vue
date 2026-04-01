<template>
	<div class="behavior-container layout-padding">
		<div class="layout-padding-auto layout-padding-view behavior-view">
				<!-- 控制栏 -->
			<div class="control-bar">
				<div class="control-group">
						<label class="control-label">行为模型</label>
						<el-select v-model="behaviorWeight" placeholder="选择行为模型" size="large" class="control-select">
						<el-option v-for="w in behaviorWeightItems" :key="w.value" :label="w.label" :value="w.value" />
					</el-select>
				</div>

				<div class="control-group">
						<label class="control-label">计数模型</label>
						<el-select v-model="countsWeight" placeholder="选择人头计数模型" size="large" class="control-select">
						<el-option v-for="w in countsWeightItems" :key="w.value" :label="w.label" :value="w.value" />
					</el-select>
				</div>

					<div class="control-group">
						<label class="control-label">置信度</label>
					<div class="slider-wrapper">
						<el-slider v-model="conf" :min="1" :max="99" :format-tooltip="formatTooltip" class="control-slider" />
						<span class="slider-value">{{ (conf / 100).toFixed(2) }}</span>
					</div>
				</div>
			</div>

				<!-- 按钮栏 -->
			<div class="button-bar">
				<el-upload
					v-model="state.img"
					ref="uploadFile"
					class="upload-button-wrapper"
					action="/flask/files/upload"
					:show-file-list="false"
					:on-success="handleUploadSuccess"
				>
					<el-button type="primary" size="large" class="upload-trigger-button">
						<el-icon class="upload-btn-icon"><Plus /></el-icon>
							<span>上传图片</span>
					</el-button>
				</el-upload>
				<el-tag v-if="uploadFileName" type="success" class="upload-file-tag" :title="uploadFileName">
						✓ {{ truncateFileName(uploadFileName, 20) }}
				</el-tag>
				<el-button type="primary" @click="runDual" :loading="isLoading" class="action-button">
					<span>双模型检测</span>
				</el-button>
				<el-button type="primary" @click="runAnalyze" :loading="isLoading" class="action-button">
						<span>🤖 AI 分析</span>
				</el-button>
				<el-divider direction="vertical" />
					<el-checkbox v-model="preferManualAnalysis" label="自定义JSON分析" />
					<el-input v-model="manualAnalysisJsonPath" placeholder="JSON文件路径" size="large" clearable class="json-path-input" />
				<el-button :disabled="!analysisMarkdown" @click="copyReport" class="secondary-button">
						<span>📋 复制报告</span>
				</el-button>
				<el-button :disabled="!analysisJson" @click="downloadJson" class="secondary-button">
						<span>⬇️ 下载JSON</span>
				</el-button>
			</div>

				<!-- 结果区 -->
			<div class="result-section" v-if="result">
				<el-row :gutter="20">
					<el-col :xs="24" :md="12" class="result-col">
						<el-card class="result-card" shadow="hover">
							<template #header>
								<div class="result-header">
									<span>上传图片预览</span>
								</div>
							</template>
							<div class="preview-image-wrap">
								<img v-if="originalPreviewUrl" :src="originalPreviewUrl" class="preview-image-lg" alt="上传图片预览" />
								<div v-else class="preview-empty">暂无上传图片</div>
							</div>
						</el-card>
					</el-col>

					<el-col :xs="24" :md="12" class="result-col">
						<el-card class="result-card" shadow="hover">
							<template #header>
								<div class="result-header">
									<span>处理结果预览</span>
								</div>
							</template>
							<div class="preview-image-wrap">
								<img v-if="processedPreviewUrl" :src="processedPreviewUrl" class="preview-image-lg" alt="处理结果预览" />
								<div v-else class="preview-empty">请先执行双模型检测，或后端未返回画框结果图</div>
							</div>
						</el-card>
					</el-col>

						<!-- 统计卡片 -->
					<el-col :xs="24" :sm="12" :md="8" class="result-col">
						<el-card class="result-card" shadow="hover">
							<template #header>
									<div class="result-header">
										<span>检测统计</span>
									</div>
							</template>
							<div class="stats-grid">
								<div class="stat-item" v-for="item in displayStats" :key="item.key">
									<span class="stat-label">{{ item.label }}</span>
									<span class="stat-value">{{ item.value }}</span>
								</div>
							</div>
						</el-card>
					</el-col>

						<!-- AI分析卡片 -->
					<el-col :xs="24" :sm="12" :md="16" class="result-col" v-if="analysisMarkdown">
						<el-card class="result-card" shadow="hover">
							<template #header>
								<div class="result-header">
										<span>🤖 AI分析报告</span>
								</div>
							</template>
							<div class="markdown-content" v-html="analysisMarkdown"></div>
						</el-card>
					</el-col>

						<!-- 可视化输出（JSON） -->
						<el-col :xs="24" class="result-col" v-if="analysisJsonText">
							<el-card class="result-card" shadow="hover">
								<template #header>
									<div class="result-header">
											<span>检测结果可视化（JSON）</span>
									</div>
								</template>
								<div class="image-container chart-showcase">
									<div class="chart-chip-list" v-if="reportChips.length">
										<span class="chart-chip" v-for="chip in reportChips" :key="chip.label">{{ chip.label }}：{{ chip.value }}</span>
									</div>
									<div class="chart-grid-board" v-if="analysisHasCharts">
										<div class="chart-tile span-6">
											<div class="tile-title">行为人数分布（柱状）</div>
											<div class="chart-canvas" ref="classBarChartRef"></div>
										</div>
										<div class="chart-tile span-6">
											<div class="tile-title">行为占比（玫瑰图）</div>
											<div class="chart-canvas" ref="classRoseChartRef"></div>
										</div>
										<div class="chart-tile span-6">
											<div class="tile-title">课堂指标雷达图</div>
											<div class="chart-canvas" ref="metricsRadarChartRef"></div>
										</div>
										<div class="chart-tile span-6">
											<div class="tile-title">指标对比（条形）</div>
											<div class="chart-canvas" ref="metricsBarChartRef"></div>
										</div>
										<div class="chart-tile span-8">
											<div class="tile-title">座位区域热力图（3x3）</div>
											<div class="chart-canvas" ref="spatialHeatmapChartRef"></div>
										</div>
										<div class="chart-tile span-4">
											<div class="tile-title">专注度仪表盘</div>
											<div class="chart-canvas" ref="focusGaugeChartRef"></div>
										</div>
										<div class="chart-tile span-6">
											<div class="tile-title">行为计数与占比（双轴）</div>
											<div class="chart-canvas" ref="classMixChartRef"></div>
										</div>
										<div class="chart-tile span-6">
											<div class="tile-title">空间剖面分布</div>
											<div class="chart-canvas" ref="spatialProfileChartRef"></div>
										</div>
										<div class="chart-tile span-12">
											<div class="tile-title">关键行为占比（环图）</div>
											<div class="chart-canvas" ref="metricRingChartRef"></div>
										</div>
									</div>
									<pre class="json-result" v-else>{{ analysisJsonText }}</pre>
									<details class="diag-panel">
										<summary>图表数据诊断面板（用于排查空图）</summary>
										<pre class="diag-json">{{ chartDiagnosticsText }}</pre>
									</details>
								</div>
							</el-card>
						</el-col>
				</el-row>
			</div>

				<!-- 空状态提示 -->
			<div class="empty-state" v-if="!result">
					<div class="empty-icon">📸</div>
					<p class="empty-text">上传图片并运行检测来查看结果</p>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts" name="behaviorPredict">
import { reactive, ref, onMounted, onBeforeUnmount, computed, watch, nextTick } from 'vue';
import type { UploadInstance, UploadProps } from 'element-plus';
import { ElMessage } from 'element-plus';
import request from '/@/utils/request';
import { Plus } from '@element-plus/icons-vue';
import * as echarts from 'echarts';

const imageUrl = ref('');
const uploadFile = ref<UploadInstance>();
const uploadFileName = ref('');
const conf = ref(25);
const behaviorWeight = ref('');
const countsWeight = ref('');
const preferManualAnalysis = ref(false);
const manualAnalysisJsonPath = ref('');
const isLoading = ref(false);
const state = reactive({
	img: '',
	weight_items: [] as any[],
});

const behaviorWeightItems = computed(() => state.weight_items.filter((w) => /student|behavior|best/i.test(w.value)));
const countsWeightItems = computed(() => state.weight_items.filter((w) => /count|head|per_counts/i.test(w.value)));

const formatTooltip = (val: number) => val / 100;

const truncateFileName = (name: string, maxLen: number = 20) => {
	if (name.length <= maxLen) return name;
	const ext = name.substring(name.lastIndexOf('.'));
	const nameWithoutExt = name.substring(0, name.lastIndexOf('.'));
	const availableLen = maxLen - ext.length - 3; // 留给...和扩展名空间
	return nameWithoutExt.substring(0, availableLen) + '...' + ext;
};

const handleUploadSuccess: UploadProps['onSuccess'] = (response, file) => {
	imageUrl.value = URL.createObjectURL(file.raw!);
	state.img = response.data; // Spring 返回的文件访问 URL
	uploadFileName.value = file.name; // 保存文件名
};

const getWeights = () => {
	// 直接走 Vite 代理到 Flask 5000
	request
		.get('/flask/file_names')
		.then((res) => {
			try {
				// 兼容三种返回：
				// 1) 直接对象 { weight_items: [...] }
				// 2) 字符串 '...json...'
				// 3) { code:0, data:'...json...' }
				let payload: any = res;
				if (typeof payload === 'string') {
					payload = JSON.parse(payload);
				} else if (payload && typeof payload.data === 'string') {
					payload = JSON.parse(payload.data);
				}
				const items = Array.isArray(payload?.weight_items) ? payload.weight_items : [];
				if (!items.length) throw new Error('empty');
				state.weight_items = items;
				// 智能预选（首次加载时）
				if (!behaviorWeight.value) {
					const cand = items.find((x: any) => /student|behavior/i.test(x.value)) || items.find((x: any) => /best_student/i.test(x.value));
					if (cand) behaviorWeight.value = cand.value;
				}
				if (!countsWeight.value) {
					const cand = items.find((x: any) => /count|head|per_counts/i.test(x.value)) || items.find((x: any) => /best_per_counts/i.test(x.value));
					if (cand) countsWeight.value = cand.value;
				}
			} catch (e: any) {
				ElMessage.error('获取模型列表失败');
			}
		})
		.catch((e) => ElMessage.error(String(e)));
};

const result = ref<any>(null);
const analysisMarkdown = ref('');
const analysisJson = ref<any>(null);
const analysisCounts = ref<Record<string, unknown>>({});
const savedBehaviorPath = ref<string>('');
const savedAnalysisJsonPath = ref<string>('');
const analysisJsonText = computed(() => (analysisJson.value ? JSON.stringify(analysisJson.value, null, 2) : ''));
const sectionMeta: Record<string, { title: string; span: number; priority: number }> = {
	summary: { title: '课堂概述', span: 6, priority: 1 },
	metrics: { title: '核心指标', span: 6, priority: 2 },
	observations: { title: '关键观察', span: 6, priority: 3 },
	risks: { title: '风险提示', span: 6, priority: 4 },
	suggestions: { title: '改进建议', span: 6, priority: 5 },
	per_class: { title: '行为分类统计', span: 6, priority: 6 },
	confidence: { title: '置信度结论', span: 3, priority: 7 },
	head: { title: '人数', span: 3, priority: 8 },
	spatial: { title: '空间信息', span: 6, priority: 9 },
	source: { title: '来源', span: 6, priority: 10 },
	provenance: { title: '处理链路', span: 6, priority: 11 },
	limitations: { title: '局限说明', span: 6, priority: 12 },
	schema_version: { title: '版本', span: 3, priority: 13 },
};

const prettifyKey = (key: string) => {
	if (sectionMeta[key]?.title) return sectionMeta[key].title;
	return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
};

const formatJsonValue = (value: unknown): string => {
	if (value === null) return 'null';
	if (typeof value === 'string') return value;
	if (typeof value === 'number' || typeof value === 'boolean') return String(value);
	try {
		return JSON.stringify(value);
	} catch {
		return String(value);
	}
};

const formatListItem = (item: unknown): string => {
	if (item && typeof item === 'object' && !Array.isArray(item)) {
		const pairs = Object.entries(item as Record<string, unknown>).map(([k, v]) => `${k}: ${formatJsonValue(v)}`);
		return pairs.join(' | ');
	}
	return formatJsonValue(item);
};

const reportSections = computed(() => {
	if (!analysisJson.value || typeof analysisJson.value !== 'object') return [];
	const data = analysisJson.value as Record<string, unknown>;
	return Object.entries(data)
		.sort(([a], [b]) => (sectionMeta[a]?.priority ?? 99) - (sectionMeta[b]?.priority ?? 99))
		.map(([key, value]) => {
			const meta = sectionMeta[key];
			if (Array.isArray(value)) {
				return {
					key,
					title: meta?.title ?? prettifyKey(key),
					span: meta?.span ?? 6,
					kind: 'array' as const,
					arrayValues: value.map((item) => formatListItem(item)),
					objectValues: [] as Array<{ key: string; value: string }>,
					valueText: '',
				};
			}
			if (value && typeof value === 'object') {
				return {
					key,
					title: meta?.title ?? prettifyKey(key),
					span: meta?.span ?? 6,
					kind: 'object' as const,
					objectValues: Object.entries(value as Record<string, unknown>).map(([k, v]) => ({
						key: prettifyKey(k),
						value: formatJsonValue(v),
					})),
					arrayValues: [] as string[],
					valueText: '',
				};
			}
			return {
				key,
				title: meta?.title ?? prettifyKey(key),
				span: meta?.span ?? 3,
				kind: 'primitive' as const,
				valueText: formatJsonValue(value),
				arrayValues: [] as string[],
				objectValues: [] as Array<{ key: string; value: string }>,
			};
		});
});

const reportChips = computed(() => {
	const data = analysisJson.value as Record<string, unknown> | null;
	if (!data) return [];
	const metrics = data.metrics && typeof data.metrics === 'object' ? (data.metrics as Record<string, unknown>) : {};
	const chips = [
		{ label: '置信度', value: formatJsonValue(data.confidence) },
		{ label: '人数', value: formatJsonValue(data.head) },
		{ label: '活跃分', value: formatJsonValue(metrics.activity_score) },
		{ label: '专注分', value: formatJsonValue(metrics.focus_score) },
	].filter((x) => x.value !== 'undefined' && x.value !== '');
	return chips;
});

const classBarChartRef = ref<HTMLElement | null>(null);
const classRoseChartRef = ref<HTMLElement | null>(null);
const metricsRadarChartRef = ref<HTMLElement | null>(null);
const metricsBarChartRef = ref<HTMLElement | null>(null);
const spatialHeatmapChartRef = ref<HTMLElement | null>(null);
const focusGaugeChartRef = ref<HTMLElement | null>(null);
const classMixChartRef = ref<HTMLElement | null>(null);
const spatialProfileChartRef = ref<HTMLElement | null>(null);
const metricRingChartRef = ref<HTMLElement | null>(null);

let classBarChart: echarts.ECharts | null = null;
let classRoseChart: echarts.ECharts | null = null;
let metricsRadarChart: echarts.ECharts | null = null;
let metricsBarChart: echarts.ECharts | null = null;
let spatialHeatmapChart: echarts.ECharts | null = null;
let focusGaugeChart: echarts.ECharts | null = null;
let classMixChart: echarts.ECharts | null = null;
let spatialProfileChart: echarts.ECharts | null = null;
let metricRingChart: echarts.ECharts | null = null;

const toNum = (value: unknown, fallback = 0) => {
	const n = Number(value);
	return Number.isFinite(n) ? n : fallback;
};

const isDisplayableUrl = (url: unknown) => {
	const text = String(url || '').trim();
	if (!text) return false;
	return /^(https?:\/\/|\/|data:image\/|blob:)/i.test(text);
};

const labelAliasMap: Record<string, string> = {
	upright: '坐姿端正',
	bow_head: '低头',
	turn_head: '转头',
	reading: '阅读',
	raise_head: '抬头',
	using_phone: '使用手机',
	phone: '手机',
	book: '书本',
	head_down_rate: '低头率',
	phone_usage_rate: '手机使用率',
	reading_rate: '阅读率',
	hand_raise_rate: '举手率',
	looking_around_rate: '东张西望率',
	writing_rate: '书写率',
	sleeping_rate: '瞌睡率',
	distracted_rate: '分心率',
	focus_score: '专注分',
	activity_score: '活跃分',
	interaction_level: '互动水平',
	head: '人数',
};

const normalizeLabelKey = (key: unknown) => {
	const raw = String(key || '').trim();
	if (!raw) return '';
	const compact = raw
		.replace(/([a-z])([A-Z])/g, '$1_$2')
		.replace(/[\s\-]+/g, '_')
		.toLowerCase();
	const alias: Record<string, string> = {
		use_phone: 'using_phone',
		usingphone: 'using_phone',
		phone_usage: 'phone_usage_rate',
		head_down: 'bow_head',
		hand_raising: 'raise_head',
		raise_hand: 'raise_head',
		hands_up: 'raise_head',
		note_taking: 'writing',
		notetaking: 'writing',
		cellphone: 'phone',
		mobile_phone: 'phone',
	};
	return alias[compact] || compact;
};

const displayLabel = (key: unknown) => {
	const normalized = normalizeLabelKey(key);
	if (labelAliasMap[normalized]) return labelAliasMap[normalized];
	return String(key || '')
		.replace(/_/g, ' ')
		.replace(/\b\w/g, (c) => c.toUpperCase());
};

const extractCountValue = (value: unknown) => {
	if (typeof value === 'number') return toNum(value, 0);
	if (typeof value === 'string') {
		try {
			const parsed = JSON.parse(value);
			return extractCountValue(parsed);
		} catch {
			return toNum(value, 0);
		}
	}
	if (value && typeof value === 'object') {
		const obj = value as Record<string, unknown>;
		if ('count' in obj) return toNum(obj.count, 0);
		if ('value' in obj) return toNum(obj.value, 0);
		if ('num' in obj) return toNum(obj.num, 0);
	}
	return toNum(value, 0);
};

const normalizeCountMap = (value: unknown) => {
	if (!value || typeof value !== 'object') return {} as Record<string, number>;
	const raw = value as Record<string, unknown>;
	const out: Record<string, number> = {};
	Object.entries(raw).forEach(([k, v]) => {
		const key = normalizeLabelKey(k);
		if (!key || /^head$|^人数$/i.test(key)) return;
		out[key] = (out[key] || 0) + extractCountValue(v);
	});
	return out;
};

const originalPreviewUrl = computed(() => {
	if (imageUrl.value) return imageUrl.value;
	if (isDisplayableUrl(state.img)) return String(state.img);
	return '';
});

const processedPreviewUrl = computed(() => {
	const candidates = [
		result.value?.outImg,
		result.value?.out_img,
	];
	for (const item of candidates) {
		if (isDisplayableUrl(item)) return String(item);
	}
	return '';
});

const prettyLabel = (key: string) => displayLabel(key);

const objectCountMap = computed(() => {
	const detections = Array.isArray(result.value?.objects)
		? result.value.objects
		: Array.isArray(result.value?.detections)
		? result.value.detections
		: [];
	const out: Record<string, number> = {};
	detections.forEach((det: any) => {
		const k = normalizeLabelKey(det?.label);
		if (!k || /^head$|^人数$/i.test(k)) return;
		out[k] = (out[k] || 0) + 1;
	});
	return out;
});

const displayStats = computed(() => {
	const countMap = normalizeCountMap(result.value?.counts);
	const source = Object.keys(countMap).length ? countMap : objectCountMap.value;
	const rows = Object.entries(source)
		.map(([key, value]) => ({
			key,
			label: displayLabel(key),
			value: toNum(value, 0),
		}))
		.sort((a, b) => b.value - a.value);
	const head = toNum(result.value?.head ?? result.value?.人数, NaN);
	if (Number.isFinite(head)) {
		rows.unshift({ key: 'head', label: '人数', value: Number(head) });
	}
	return rows;
});

type MetricEntry = {
	key: string;
	name: string;
	value: number;
	isRate: boolean;
	isScore: boolean;
};

const metricEntries = computed(() => {
	let raw = analysisJson.value?.metrics as Record<string, unknown> | undefined;
	if (!raw || typeof raw !== 'object') {
		const top = analysisJson.value && typeof analysisJson.value === 'object' ? (analysisJson.value as Record<string, unknown>) : {};
		const fallbackTop = Object.fromEntries(
			Object.entries(top).filter(([k, v]) => typeof v === 'number' && /(score|rate|ratio|focus|activity|phone|reading|sleeping|writing|head|raise|looking)/i.test(k))
		);
		raw = Object.keys(fallbackTop).length ? fallbackTop : undefined;
	}
	if (!raw || typeof raw !== 'object') return [] as MetricEntry[];
	return Object.entries(raw)
		.map(([k, v]) => {
			const key = normalizeLabelKey(k);
			return {
				key,
				name: prettyLabel(k),
				value: toNum(v, NaN),
				isRate: /rate$|ratio$/i.test(key),
				isScore: /score$/i.test(key),
			};
		})
		.filter((x) => Number.isFinite(x.value));
});

const metricMap = computed(() => {
	const map: Record<string, number> = {};
	metricEntries.value.forEach((entry) => {
		map[entry.key] = entry.value;
	});
	return map;
});

const focusMetricValue = computed(() => {
	const map = metricMap.value;
	const fromMap = map.focus_score ?? map.focus;
	if (Number.isFinite(fromMap)) return Number(fromMap);
	const fromJson = toNum(analysisJson.value?.metrics?.focus_score ?? analysisJson.value?.focus_score, NaN);
	if (Number.isFinite(fromJson)) return Number(fromJson);
	return NaN;
});

const radarMetricEntries = computed(() => {
	const entries = metricEntries.value;
	const map = metricMap.value;
	const preferredRateKeys = [
		'head_down_rate',
		'phone_usage_rate',
		'reading_rate',
		'hand_raise_rate',
		'looking_around_rate',
		'writing_rate',
		'sleeping_rate',
		'distracted_rate',
	];
	const preferred = preferredRateKeys
		.filter((k) => Number.isFinite(map[k]))
		.map((k) => ({
			key: k,
			name: displayLabel(k),
			value: toNum(map[k], 0),
			isRate: true,
			isScore: false,
		}));
	if (preferred.length >= 3) return preferred;

	const rateOnly = entries.filter((x) => x.isRate);
	if (rateOnly.length >= 3) return rateOnly.slice(0, 8);

	return entries.filter((x) => !/^focus_score$|^activity_score$/i.test(x.key)).slice(0, 8);
});

const perClassEntries = computed(() => {
	const rawPerClass = analysisJson.value?.per_class;
	let source: Record<string, unknown> = {};
	if (rawPerClass && typeof rawPerClass === 'object') {
		const normalizedSource: Record<string, unknown> = {};
		Object.entries(rawPerClass as Record<string, unknown>).forEach(([k, v]) => {
			const key = normalizeLabelKey(k);
			if (!key || /^head$|^人数$/i.test(key)) return;
			normalizedSource[key] = v;
		});
		source = normalizedSource;
	} else {
		const countMap = normalizeCountMap(analysisCounts.value);
		const resultCountMap = normalizeCountMap(result.value?.counts);
		const detectionCountMap = objectCountMap.value;
		source = Object.keys(countMap).length ? countMap : Object.keys(resultCountMap).length ? resultCountMap : detectionCountMap;
	}
	if (!source || !Object.keys(source).length) return [] as Array<{ name: string; count: number; rate: number }>;
	const headFromJson = toNum(analysisJson.value?.head ?? analysisJson.value?.人数, NaN);
	const headFromResult = toNum(result.value?.head ?? result.value?.人数, NaN);
	return Object.entries(source).map(([k, v]) => {
		let current = v;
		if (typeof current === 'string') {
			try {
				current = JSON.parse(current);
			} catch {
				// ignore
			}
		}
		if (current && typeof current === 'object') {
			const obj = current as Record<string, unknown>;
			const countVal = toNum(obj.count, 0);
			const autoHead = Number.isFinite(headFromJson) ? headFromJson : Number.isFinite(headFromResult) ? headFromResult : 0;
			const autoRate = autoHead > 0 ? Math.round((countVal / autoHead) * 100) : 0;
			return {
				name: prettyLabel(k),
				count: countVal,
				rate: toNum(obj.rate, autoRate),
			};
		}
		const countVal = toNum(current, 0);
		const autoHead = Number.isFinite(headFromJson) ? headFromJson : Number.isFinite(headFromResult) ? headFromResult : 0;
		const autoRate = autoHead > 0 ? Math.round((countVal / autoHead) * 100) : 0;
		return {
			name: prettyLabel(k),
			count: countVal,
			rate: autoRate,
		};
	});
});

const deriveSpatialMatrixFromDetections = () => {
	const detections = Array.isArray(result.value?.objects)
		? result.value.objects
		: Array.isArray(result.value?.detections)
		? result.value.detections
		: [];
	if (!detections.length) return [] as number[][];

	const width =
		toNum(result.value?.size?.width, 0) ||
		toNum(result.value?.image_size?.[0], 0) ||
		toNum(analysisJson.value?.source?.image_size?.width, 0);
	const height =
		toNum(result.value?.size?.height, 0) ||
		toNum(result.value?.image_size?.[1], 0) ||
		toNum(analysisJson.value?.source?.image_size?.height, 0);
	if (width <= 0 || height <= 0) return [] as number[][];

	const grid = [
		[0, 0, 0],
		[0, 0, 0],
		[0, 0, 0],
	];
	detections.forEach((det: any) => {
		const bbox = det?.bbox_xyxy || det?.bbox;
		if (!Array.isArray(bbox) || bbox.length < 4) return;
		const x1 = toNum(bbox[0], NaN);
		const y1 = toNum(bbox[1], NaN);
		const x2 = toNum(bbox[2], NaN);
		const y2 = toNum(bbox[3], NaN);
		if (![x1, y1, x2, y2].every(Number.isFinite)) return;
		const cx = (x1 + x2) / 2;
		const cy = (y1 + y2) / 2;
		const col = Math.min(2, Math.max(0, Math.floor((cx / width) * 3)));
		const row = Math.min(2, Math.max(0, Math.floor((cy / height) * 3)));
		grid[row][col] += 1;
	});
	return grid;
};

const spatialMatrix = computed(() => {
	let grid = analysisJson.value?.spatial?.grid3x3 as unknown;
	if (!grid) {
		grid = analysisJson.value?.grid3x3 as unknown;
	}
	if (typeof grid === 'string') {
		try {
			grid = JSON.parse(grid);
		} catch {
			return deriveSpatialMatrixFromDetections();
		}
	}
	if (!Array.isArray(grid)) return [] as number[][];
	if (grid.length === 3 && Array.isArray(grid[0])) {
		return (grid as unknown[]).map((row) => (Array.isArray(row) ? row.map((v) => toNum(v, 0)) : [0, 0, 0]));
	}
	if (grid.length === 9) {
		const nums = (grid as unknown[]).map((v) => toNum(v, 0));
		return [nums.slice(0, 3), nums.slice(3, 6), nums.slice(6, 9)];
	}
	return deriveSpatialMatrixFromDetections();
});

const spatialProfile = computed(() => {
	const matrix = spatialMatrix.value.length ? spatialMatrix.value : [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
	const rowSums = matrix.map((row) => row.reduce((sum, current) => sum + toNum(current, 0), 0));
	const colSums = [0, 1, 2].map((col) => matrix.reduce((sum, row) => sum + toNum(row[col], 0), 0));
	return {
		rowSums,
		colSums,
	};
});

const hasClassData = computed(() => perClassEntries.value.some((x) => x.count > 0 || x.rate > 0));
const hasMetricData = computed(() => metricEntries.value.length > 0);
const hasSpatialData = computed(() => spatialMatrix.value.length > 0 && spatialMatrix.value.some((row) => row.some((v) => toNum(v, 0) > 0)));
const analysisHasCharts = computed(() => hasClassData.value || hasMetricData.value || hasSpatialData.value);
const chartDiagnostics = computed(() => {
	const classData = perClassEntries.value;
	const metricsData = metricEntries.value;
	const matrix = spatialMatrix.value;
	const sourceCounts = normalizeCountMap(result.value?.counts);
	const objectCounts = objectCountMap.value;
	return {
		hasCharts: analysisHasCharts.value,
		flags: {
			hasClassData: hasClassData.value,
			hasMetricData: hasMetricData.value,
			hasSpatialData: hasSpatialData.value,
		},
		sources: {
			analysisJsonExists: !!analysisJson.value,
			analysisCountsKeys: Object.keys(analysisCounts.value || {}),
			resultCountsKeys: Object.keys(sourceCounts),
			objectCountKeys: Object.keys(objectCounts),
		},
		classData: {
			length: classData.length,
			totalCount: classData.reduce((sum, item) => sum + toNum(item.count, 0), 0),
			top: classData.slice(0, 8),
		},
		metricsData: {
			length: metricsData.length,
			top: metricsData.slice(0, 10),
		},
		radarData: {
			length: radarMetricEntries.value.length,
			top: radarMetricEntries.value.slice(0, 8),
		},
		spatialData: {
			matrixSize: matrix.length ? `${matrix.length}x${matrix[0]?.length || 0}` : '0x0',
			matrix,
			nonZeroCells: matrix.flat().filter((v) => toNum(v, 0) > 0).length,
		},
		preview: {
			processedPreviewUrl: processedPreviewUrl.value || null,
			head: result.value?.head ?? result.value?.人数 ?? null,
			focusMetricValue: Number.isFinite(focusMetricValue.value) ? focusMetricValue.value : null,
		},
	};
});
const chartDiagnosticsText = computed(() => JSON.stringify(chartDiagnostics.value, null, 2));

const disposeVisualizationCharts = () => {
	classBarChart?.dispose();
	classRoseChart?.dispose();
	metricsRadarChart?.dispose();
	metricsBarChart?.dispose();
	spatialHeatmapChart?.dispose();
	focusGaugeChart?.dispose();
	classMixChart?.dispose();
	spatialProfileChart?.dispose();
	metricRingChart?.dispose();
	classBarChart = null;
	classRoseChart = null;
	metricsRadarChart = null;
	metricsBarChart = null;
	spatialHeatmapChart = null;
	focusGaugeChart = null;
	classMixChart = null;
	spatialProfileChart = null;
	metricRingChart = null;
};

const resizeVisualizationCharts = () => {
	classBarChart?.resize();
	classRoseChart?.resize();
	metricsRadarChart?.resize();
	metricsBarChart?.resize();
	spatialHeatmapChart?.resize();
	focusGaugeChart?.resize();
	classMixChart?.resize();
	spatialProfileChart?.resize();
	metricRingChart?.resize();
};

const initVisualizationCharts = () => {
	if (!analysisHasCharts.value) {
		disposeVisualizationCharts();
		return;
	}
	if (
		!classBarChartRef.value ||
		!classRoseChartRef.value ||
		!metricsRadarChartRef.value ||
		!metricsBarChartRef.value ||
		!spatialHeatmapChartRef.value ||
		!focusGaugeChartRef.value ||
		!classMixChartRef.value ||
		!spatialProfileChartRef.value ||
		!metricRingChartRef.value
	) {
		return;
	}

	disposeVisualizationCharts();
	classBarChart = echarts.init(classBarChartRef.value);
	classRoseChart = echarts.init(classRoseChartRef.value);
	metricsRadarChart = echarts.init(metricsRadarChartRef.value);
	metricsBarChart = echarts.init(metricsBarChartRef.value);
	spatialHeatmapChart = echarts.init(spatialHeatmapChartRef.value);
	focusGaugeChart = echarts.init(focusGaugeChartRef.value);
	classMixChart = echarts.init(classMixChartRef.value);
	spatialProfileChart = echarts.init(spatialProfileChartRef.value);
	metricRingChart = echarts.init(metricRingChartRef.value);

	const classData = perClassEntries.value;
	const metricsData = metricEntries.value;
	const radarData = radarMetricEntries.value;
	const heat = spatialMatrix.value;
	const palette = ['#0ea5e9', '#14b8a6', '#22c55e', '#f59e0b', '#f97316', '#ef4444', '#8b5cf6', '#3b82f6'];
	const axisLabelStyle = { color: '#334155', fontSize: 12 };
	const splitLineStyle = { lineStyle: { color: 'rgba(148, 163, 184, 0.25)' } };
	const setNoDataOption = (chart: echarts.ECharts, title = '暂无数据') => {
		chart.setOption({
			animation: false,
			title: {
				text: title,
				left: 'center',
				top: 'middle',
				textStyle: { color: '#94a3b8', fontSize: 16, fontWeight: 500 },
			},
			xAxis: { show: false },
			yAxis: { show: false },
			series: [],
		});
	};

	const barNames = classData.map((x) => x.name);
	const barVals = classData.map((x) => x.count);
	const classRateVals = classData.map((x) => x.rate);

	if (classData.length) {
		classBarChart.setOption({
		color: [palette[0]],
		textStyle: { color: '#334155', fontSize: 12 },
		tooltip: { trigger: 'axis', confine: true },
		grid: { left: 56, right: 24, top: 28, bottom: 62 },
		xAxis: {
			type: 'category',
			data: barNames,
			axisLabel: { ...axisLabelStyle, interval: 0, rotate: 16 },
			axisLine: { lineStyle: { color: '#94a3b8' } },
		},
		yAxis: {
			type: 'value',
			name: '人数',
			nameTextStyle: { color: '#475569', fontSize: 12, padding: [0, 0, 4, 0] },
			axisLabel: axisLabelStyle,
			splitLine: splitLineStyle,
		},
		series: [
			{
				type: 'bar',
				data: barVals,
				barWidth: '48%',
				itemStyle: {
					borderRadius: [8, 8, 0, 0],
					color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
						{ offset: 0, color: '#0ea5e9' },
						{ offset: 1, color: '#0284c7' },
					]),
				},
			},
		],
	});
	} else {
		setNoDataOption(classBarChart, '行为分类数据缺失');
	}

	if (classData.length) {
		classRoseChart.setOption({
		textStyle: { color: '#334155', fontSize: 12 },
		tooltip: { trigger: 'item', confine: true },
		legend: {
			type: 'scroll',
			bottom: 0,
			icon: 'circle',
			itemWidth: 10,
			itemHeight: 10,
			textStyle: { color: '#334155', fontSize: 12 },
		},
		color: palette,
		series: [
			{
				type: 'pie',
				radius: ['30%', '72%'],
				center: ['50%', '42%'],
				roseType: 'radius',
				itemStyle: { borderRadius: 6 },
				label: { show: false },
				labelLine: { show: false },
				emphasis: { label: { show: true, formatter: '{b}\n{d}%', fontSize: 13, fontWeight: 700 } },
				data: classData.map((x) => ({ name: x.name, value: x.count || x.rate || 0 })),
			},
		],
	});
	} else {
		setNoDataOption(classRoseChart, '行为分类数据缺失');
	}

	const radarBase = (radarData.length ? radarData : metricsData).slice(0, 8);
	if (radarBase.length) {
		metricsRadarChart.setOption({
		textStyle: { color: '#334155', fontSize: 12 },
		tooltip: {},
		radar: {
			radius: '65%',
			name: { color: '#475569', fontSize: 12 },
			splitLine: splitLineStyle,
			splitArea: { areaStyle: { color: ['rgba(14, 165, 233, 0.03)', 'rgba(14, 165, 233, 0.06)'] } },
			indicator: radarBase.map((x) => ({ name: x.name, max: Math.max(100, Math.ceil(x.value * 1.25)) })),
		},
		series: [
			{
				type: 'radar',
				areaStyle: { color: 'rgba(14,165,233,0.25)' },
				lineStyle: { color: '#0284c7', width: 2 },
				data: [{ value: radarBase.map((x) => x.value), name: '课堂指标' }],
			},
		],
	});
	} else {
		setNoDataOption(metricsRadarChart, '指标数据缺失');
	}

	const metricSort = [...metricsData].sort((a, b) => b.value - a.value).slice(0, 10);
	if (metricSort.length) {
		metricsBarChart.setOption({
		color: [palette[2]],
		textStyle: { color: '#334155', fontSize: 12 },
		tooltip: { trigger: 'axis', confine: true },
		grid: { left: 162, right: 22, top: 28, bottom: 34 },
		xAxis: { type: 'value', axisLabel: axisLabelStyle, splitLine: splitLineStyle },
		yAxis: {
			type: 'category',
			data: metricSort.map((x) => x.name),
			axisLabel: { ...axisLabelStyle, width: 132, overflow: 'truncate' },
		},
		series: [{ type: 'bar', data: metricSort.map((x) => x.value), barWidth: '58%', itemStyle: { borderRadius: [0, 6, 6, 0] } }],
	});
	} else {
		setNoDataOption(metricsBarChart, '指标数据缺失');
	}

	const matrix = heat.length ? heat : [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
	const heatData: Array<[number, number, number]> = [];
	for (let r = 0; r < 3; r++) {
		for (let c = 0; c < 3; c++) {
			heatData.push([c, 2 - r, toNum(matrix[r]?.[c], 0)]);
		}
	}
	const heatMax = Math.max(...heatData.map((x) => x[2]), 1);
	const heatColors = ['#f1e9a8', '#e9ca96', '#d47c72', '#bd3f4d'];
	if (hasSpatialData.value) {
		try {
			spatialHeatmapChart.setOption({
				textStyle: { color: '#334155', fontSize: 12 },
				tooltip: { position: 'top' },
				grid: { left: 54, right: 24, top: 28, bottom: 24 },
				xAxis: { type: 'category', data: ['左区', '中区', '右区'], axisLabel: { ...axisLabelStyle, fontSize: 13 } },
				yAxis: { type: 'category', data: ['后排', '中排', '前排'], axisLabel: { ...axisLabelStyle, fontSize: 13 } },
				visualMap: {
					show: false,
					min: 0,
					max: Math.max(1, heatMax),
					inRange: { color: heatColors },
					calculable: false,
				},
				series: [
					{
						type: 'heatmap',
						data: heatData,
						label: { show: true, color: '#0f172a', fontSize: 14, fontWeight: 700 },
						itemStyle: {
							borderRadius: 6,
							borderColor: '#fff',
							borderWidth: 1.6,
						},
					},
				],
			});
		} catch (err) {
			console.error('[behaviorPredict] heatmap render failed', err);
			setNoDataOption(spatialHeatmapChart, '热力图渲染失败');
		}
	} else {
		setNoDataOption(spatialHeatmapChart, '空间分布数据缺失');
	}

	const focusMetric = Number.isFinite(focusMetricValue.value) ? focusMetricValue.value : NaN;
	if (Number.isFinite(focusMetric)) {
		focusGaugeChart.setOption({
		color: ['#0ea5e9'],
		textStyle: { color: '#334155', fontSize: 12 },
		series: [
			{
				type: 'gauge',
				startAngle: 210,
				endAngle: -30,
				min: 0,
				max: 100,
				progress: { show: true, width: 18, roundCap: true },
				axisLine: { lineStyle: { width: 18 } },
				axisTick: { show: false },
				splitLine: { show: false },
				axisLabel: { distance: -28, color: '#64748b', fontSize: 11 },
				detail: { valueAnimation: true, formatter: '{value}分', color: '#0f766e', fontSize: 26, offsetCenter: [0, '30%'] },
				title: { show: true, offsetCenter: [0, '72%'], color: '#334155', fontSize: 12 },
				data: [{ value: Math.max(0, Math.min(100, Number(focusMetric))), name: '专注分' }],
			},
		],
	});
	} else {
		setNoDataOption(focusGaugeChart, '专注度数据缺失');
	}

	if (classData.length) {
		classMixChart.setOption({
		legend: {
			top: 0,
			textStyle: { color: '#334155', fontSize: 12 },
		},
		tooltip: { trigger: 'axis' },
		grid: { left: 58, right: 58, top: 42, bottom: 66 },
		xAxis: {
			type: 'category',
			data: barNames,
			axisLabel: { ...axisLabelStyle, interval: 0, rotate: 14 },
			axisLine: { lineStyle: { color: '#94a3b8' } },
		},
		yAxis: [
			{ type: 'value', name: '人数', nameTextStyle: { color: '#475569' }, axisLabel: axisLabelStyle, splitLine: splitLineStyle },
			{ type: 'value', name: '占比(%)', min: 0, max: 100, nameTextStyle: { color: '#475569' }, axisLabel: axisLabelStyle, splitLine: { show: false } },
		],
		series: [
			{
				name: '人数',
				type: 'bar',
				data: barVals,
				barWidth: '44%',
				itemStyle: { borderRadius: [7, 7, 0, 0], color: '#14b8a6' },
			},
			{
				name: '占比',
				type: 'line',
				yAxisIndex: 1,
				data: classRateVals,
				smooth: true,
				showSymbol: false,
				lineStyle: { width: 3, color: '#f59e0b' },
				areaStyle: { color: 'rgba(245, 158, 11, 0.2)' },
			},
		],
	});
	} else {
		setNoDataOption(classMixChart, '行为分类数据缺失');
	}

	const { rowSums, colSums } = spatialProfile.value;
	const spatialProfileData = [rowSums[0], rowSums[1], rowSums[2], colSums[0], colSums[1], colSums[2]];
	if (hasSpatialData.value) {
		spatialProfileChart.setOption({
		tooltip: { trigger: 'axis' },
		textStyle: { color: '#334155', fontSize: 12 },
		grid: { left: 56, right: 24, top: 28, bottom: 42 },
		xAxis: {
			type: 'category',
			data: ['前排', '中排', '后排', '左区', '中区', '右区'],
			axisLabel: { ...axisLabelStyle, fontSize: 13 },
		},
		yAxis: { type: 'value', name: '人数', axisLabel: axisLabelStyle, splitLine: splitLineStyle },
		series: [
			{
				type: 'bar',
				data: spatialProfileData,
				itemStyle: {
					borderRadius: [8, 8, 0, 0],
					color: (params: any) => (params.dataIndex <= 2 ? '#3b82f6' : '#10b981'),
				},
			},
		],
	});
	} else {
		setNoDataOption(spatialProfileChart, '空间分布数据缺失');
	}

	const ringClassData = classData
		.map((x) => ({ name: x.name, value: x.rate > 0 ? x.rate : x.count }))
		.filter((x) => x.value > 0)
		.sort((a, b) => b.value - a.value)
		.slice(0, 8);
	const ringFallback = metricsData
		.slice()
		.sort((a, b) => b.value - a.value)
		.slice(0, 8)
		.map((x) => ({ name: x.name, value: x.value }));
	const ringData = ringClassData.length ? ringClassData : ringFallback;
	const ringTotal = ringData.reduce((sum, item) => sum + item.value, 0);
	if (ringData.length) {
		metricRingChart.setOption({
		color: palette,
		tooltip: { trigger: 'item' },
		legend: {
			type: 'scroll',
			right: '4%',
			top: 'middle',
			orient: 'vertical',
			icon: 'roundRect',
			itemWidth: 14,
			itemHeight: 10,
			textStyle: { color: '#334155', fontSize: 13 },
		},
		series: [
			{
				type: 'pie',
				radius: ['38%', '70%'],
				center: ['33%', '50%'],
				data: ringData,
				itemStyle: { borderRadius: 10, borderColor: '#fff', borderWidth: 2 },
				label: { show: false },
				labelLine: { show: false },
				emphasis: {
					label: { show: true, formatter: '{b}: {d}%', fontWeight: 700, fontSize: 13 },
				},
			},
		],
		graphic: [
			{
				type: 'text',
				left: '31%',
				top: '42%',
				style: {
					text: `${Math.round(ringTotal)}`,
					textAlign: 'center',
					fill: '#0f766e',
					font: '700 28px "Segoe UI", sans-serif',
				},
			},
			{
				type: 'text',
				left: '31%',
				top: '55%',
				style: {
					text: '合计',
					textAlign: 'center',
					fill: '#64748b',
					font: '500 13px "Segoe UI", sans-serif',
				},
			},
		],
	});
	} else {
		setNoDataOption(metricRingChart, '可视化数据缺失');
	}
};

watch(
	[analysisJson, result, analysisCounts],
	() => {
		nextTick(() => {
			initVisualizationCharts();
		});
	},
	{ deep: true }
);

const runDual = () => {
	if (!state.img) return ElMessage.warning('请先上传图片');
	const wantOrt = (behaviorWeight.value || '').toLowerCase().endsWith('.onnx') || (countsWeight.value || '').toLowerCase().endsWith('.onnx');
	const payload = {
		inputImg: state.img, // 支持 URL
		behavior_weight: behaviorWeight.value || './weights/best_student.pt',
		counts_weight: countsWeight.value || './weights/best_per_counts.pt',
		conf: conf.value / 100,
		imgsz: 640,
		backend: wantOrt ? 'onnxruntime' : undefined,
		save_json: true,
	};
	isLoading.value = true;
	request
		.post('/flask/dualDetect', payload)
		.then((res) => {
			if (res.status === 200) {
				result.value = res;
				savedBehaviorPath.value = res?.saved_paths?.behavior_json || '';
				const dbSave = res?.db_save;
				if (dbSave && dbSave.success === false) {
					ElMessage.warning(dbSave.error || '检测完成，但行为数据入库失败，BI 页面不会新增记录');
				} else {
					ElMessage.success('检测完成，已写入 BI 数据');
				}
			} else {
				ElMessage.error(res.message || '检测失败');
			}
		})
		.catch((e) => ElMessage.error(String(e)))
		.finally(() => {
			isLoading.value = false;
		});
};

const runAnalyze = () => {
	if (!state.img) return ElMessage.warning('请先上传图片');
	const wantOrt = (behaviorWeight.value || '').toLowerCase().endsWith('.onnx');
	// 1) 若勾选“使用指定AI化JSON”，则直接复用该JSON
	if (preferManualAnalysis.value && manualAnalysisJsonPath.value) {
		const payloadReuseDirect: any = {
			analysis_json_path: manualAnalysisJsonPath.value,
			title: '课堂行为分析',
		};
		return request
			.post('/flask/analyze', payloadReuseDirect)
			.then((res) => {
				if (res.status === 200) {
					analysisMarkdown.value = res.analysis_markdown || '';
					analysisJson.value = res.analysis_json || null;
					analysisCounts.value = normalizeCountMap(res.counts || {});
					savedAnalysisJsonPath.value = res.saved_analysis_json_path || manualAnalysisJsonPath.value;
					ElMessage.success('分析完成(使用指定AI化JSON)');
				} else {
					ElMessage.error(res.message || '分析失败');
				}
			})
			.catch((e) => ElMessage.error(String(e)))
			.finally(() => {
				isLoading.value = false;
			});
	}
	// 若已有已AI化的 JSON，优先直接复用，避免重复调用模型
	if (savedAnalysisJsonPath.value) {
		const payloadReuse: any = {
			analysis_json_path: savedAnalysisJsonPath.value,
			title: '课堂行为分析',
		};
		isLoading.value = true;
		return request
			.post('/flask/analyze', payloadReuse)
			.then((res) => {
				if (res.status === 200) {
					analysisMarkdown.value = res.analysis_markdown || '';
					analysisJson.value = res.analysis_json || null;
					analysisCounts.value = normalizeCountMap(res.counts || {});
					// 维持当前 savedAnalysisJsonPath（或更新为后端返回路径）
					savedAnalysisJsonPath.value = res.saved_analysis_json_path || savedAnalysisJsonPath.value;
					ElMessage.success('分析完成(复用)');
				} else {
					ElMessage.error(res.message || '分析失败');
				}
			})
			.catch((e) => ElMessage.error(String(e)))
			.finally(() => {
				isLoading.value = false;
			});
	}
	// 若尚未运行双模型检测，则先跑一遍保证严格流程
	const ensureDual = () => {
		if (savedBehaviorPath.value) return Promise.resolve({ ok: true });
		const payloadDual = {
			inputImg: state.img,
			behavior_weight: behaviorWeight.value || './weights/best_student.pt',
			counts_weight: countsWeight.value || './weights/best_per_counts.pt',
			conf: conf.value / 100,
			imgsz: 640,
			backend: wantOrt ? 'onnxruntime' : undefined,
			save_json: true,
		};
		return request.post('/flask/dualDetect', payloadDual).then((res) => {
			if (res.status === 200) {
				result.value = res;
				savedBehaviorPath.value = res?.saved_paths?.behavior_json || '';
				return { ok: true };
			}
			throw new Error(res.message || '双模型检测失败');
		});
	};

	ensureDual()
		.then(() => {
			// 严格流程：仅用 behavior_json_path 驱动 AI 化与可视化
			const payload: any = {
				two_stage: true,
				json_only: true,
				save_json_out: true,
				strict_pipeline: true,
				behavior_json_path: savedBehaviorPath.value,
			};
			try {
				const norm = savedBehaviorPath.value.replace(/\\\\/g, '/').replace(/\\/g, '/');
				const segs = norm.split('/');
				if (segs.length > 1) payload.out_dir = segs.slice(0, -1).join('/');
				// 如果行为 JSON 命名为 input_behavior.json，则将分析结果命名为 input_analysis.json
				const fname = segs[segs.length - 1] || '';
				if (/^input_behavior\.json$/i.test(fname)) {
					payload.out_stem = 'input_analysis';
				}
			} catch (e) {
				/* ignore */
			}

			request
				.post('/flask/analyze', payload)
				.then((res) => {
					if (res.status === 200) {
						analysisMarkdown.value = res.analysis_markdown || '';
						analysisJson.value = res.analysis_json || null;
						analysisCounts.value = normalizeCountMap(res.counts || {});
						savedAnalysisJsonPath.value = res.saved_analysis_json_path || '';
						ElMessage.success('分析完成');
					} else {
						ElMessage.error(res.message || '分析失败');
					}
				})
				.catch((e) => ElMessage.error(String(e)))
				.finally(() => {
					isLoading.value = false;
				});
		})
		.catch((e: any) => {
			ElMessage.error(String(e));
			isLoading.value = false;
		});
};

const copyReport = async () => {
	if (!analysisMarkdown.value) return;
	try {
		await navigator.clipboard.writeText(analysisMarkdown.value);
		ElMessage.success('已复制到剪贴板');
	} catch (e) {
		ElMessage.error('复制失败');
	}
};

const downloadJson = () => {
	if (!analysisJson.value) return;
	try {
		const blob = new Blob([JSON.stringify(analysisJson.value, null, 2)], { type: 'application/json;charset=utf-8' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = 'analysis.json';
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);
		URL.revokeObjectURL(url);
	} catch (e) {
		ElMessage.error('下载失败');
	}
};

onMounted(() => {
	getWeights();
	window.addEventListener('resize', resizeVisualizationCharts);
});

onBeforeUnmount(() => {
	window.removeEventListener('resize', resizeVisualizationCharts);
	disposeVisualizationCharts();
});
</script>

<style scoped lang="scss">
.behavior-container {
	width: 100%;
	height: 100%;
	display: flex;
	flex-direction: column;
}

.behavior-view {
	overflow-y: auto;
	display: flex;
	flex-direction: column;
	gap: 20px;
	padding: 24px !important;
	background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%);
	min-height: 0;
}

/* 控制栏 */
.control-bar {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
	gap: 16px;
	padding: 20px;
	background: var(--tech-white);
	border: 1px solid var(--tech-border-color);
	border-radius: 12px;
	box-shadow: var(--tech-shadow-sm);
	transition: all var(--tech-transition-base);

	&:hover {
		box-shadow: var(--tech-shadow-md);
	}
}

.control-group {
	display: flex;
	flex-direction: column;
	gap: 8px;

	.control-label {
		font-size: 13px;
		font-weight: 600;
		color: var(--tech-text-primary);
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.control-select {
		width: 100%;
	}
}

.slider-wrapper {
	display: flex;
	align-items: center;
	gap: 12px;

	.control-slider {
		flex: 1;
	}

	.slider-value {
		min-width: 50px;
		font-weight: 600;
		color: var(--tech-primary);
		font-size: 14px;
		text-align: right;
	}
}

/* 按钮栏 */
.button-bar {
	display: flex;
	align-items: center;
	gap: 12px;
	flex-wrap: wrap;
	padding: 16px 20px;
	background: var(--tech-white);
	border: 1px solid var(--tech-border-color);
	border-radius: 12px;
	box-shadow: var(--tech-shadow-sm);

	.el-button + .el-button {
		margin-left: 0 !important;
	}
  
	.action-button {
		font-weight: 600;
		letter-spacing: 0.5px;
		white-space: nowrap;
		min-width: 140px;
	}

	.secondary-button {
		background: var(--tech-white);
		border: 1px solid var(--tech-border-color);
		color: var(--tech-text-secondary);

		&:hover:not(:disabled) {
			background: var(--tech-bg-secondary);
			border-color: var(--tech-primary);
			color: var(--tech-primary);
		}

		&:disabled {
			opacity: 0.5;
			cursor: not-allowed;
		}
	}

	.json-path-input {
		flex: 1;
		min-width: 200px;
	}
}

.upload-file-tag {
	font-weight: 500;
	letter-spacing: 0.5px;
	max-width: 200px;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.el-divider {
	margin: 0 4px;
}

/* 上传区 */
.upload-section {
	flex: 0 0 auto;
	margin-bottom: 20px;
	width: 320px;
	height: 320px;
}

/* 上传按钮 */
.upload-button-wrapper {
	:deep(.el-upload) {
		display: inline-block;
	}
}

.upload-trigger-button {
	font-weight: 600;
	letter-spacing: 0.5px;
	white-space: nowrap;
	.upload-btn-icon {
		margin-right: 6px;
	}
}

/* 结果区 */
.result-section {
	flex: 1;
	overflow-y: auto;
}

.result-col {
	margin-bottom: 20px;
}

.result-card {
	height: 100%;
	border: 1px solid var(--tech-border-color);
	border-radius: 12px;
	overflow: hidden;
	transition: all var(--tech-transition-base);

	&:hover {
		box-shadow: var(--tech-shadow-lg);
		border-color: var(--tech-primary-light);
	}

	:deep(.el-card__header) {
		background: linear-gradient(135deg, var(--tech-primary-lighter) 0%, var(--tech-accent-light) 100%);
		border: none;
		padding: 16px 20px;

		.result-header {
			display: flex;
			align-items: center;
			gap: 8px;
			font-weight: 600;
			color: var(--tech-primary);
			font-size: 15px;
			letter-spacing: 0.5px;
		}
	}
}

/* 统计网格 */
.stats-grid {
	display: flex;
	flex-direction: column;
	gap: 0;
	border: 1px solid rgba(15, 118, 110, 0.14);
	border-radius: 12px;
	overflow: hidden;
	background: #ffffff;
}

.stat-item {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 12px 14px;
	background: #ffffff;
	border-bottom: 1px solid rgba(15, 118, 110, 0.1);

	&:last-child {
		border-bottom: none;
	}

	.stat-label {
		font-size: 14px;
		color: #334155;
		font-weight: 500;
		margin-bottom: 0;
	}

	.stat-value {
		font-size: 18px;
		font-weight: 700;
		color: #0f766e;
		line-height: 1;
	}
}

/* Markdown 内容 */
.markdown-content {
	white-space: pre-wrap;
	line-height: 1.8;
	color: var(--tech-text-secondary);
	font-family: 'Courier New', monospace;
	font-size: 13px;
	max-height: 520px;
	overflow-y: auto;
	padding: 4px 0;

	:deep(p) {
		margin-bottom: 12px;
	}

	:deep(code) {
		background: var(--tech-bg-secondary);
		padding: 2px 6px;
		border-radius: 4px;
		color: var(--tech-primary);
		font-weight: 500;
	}
}

/* 图片容器 */
.image-container {
	display: flex;
	align-items: stretch;
	justify-content: flex-start;
	background: var(--tech-bg-secondary);
	border-radius: 8px;
	min-height: 200px;
	overflow: hidden;
	width: 100%;
}

.result-image {
	width: 100%;
	max-height: 600px;
	object-fit: contain;
	border-radius: 8px;
}

.preview-image-wrap {
	min-height: 260px;
	border: 1px dashed rgba(15, 118, 110, 0.2);
	border-radius: 12px;
	background: linear-gradient(180deg, #ffffff, #f3faf8);
	display: flex;
	align-items: center;
	justify-content: center;
	padding: 12px;
}

.preview-image-lg {
	width: 100%;
	max-height: 420px;
	object-fit: contain;
	border-radius: 10px;
}

.preview-empty {
	font-size: 14px;
	color: #64748b;
	font-weight: 600;
}

.json-result {
	width: 100%;
	max-height: 600px;
	margin: 0;
	overflow: auto;
	white-space: pre-wrap;
	word-break: break-all;
	font-family: 'Consolas', 'Courier New', monospace;
	font-size: 12px;
	line-height: 1.6;
	color: var(--tech-text-primary);
	padding: 14px;
	background: #ffffff;
	border: 1px solid var(--tech-border-color);
	border-radius: 8px;
}

.diag-panel {
	margin-top: 10px;
	border: 1px dashed rgba(15, 118, 110, 0.32);
	border-radius: 10px;
	background: rgba(255, 255, 255, 0.7);
	padding: 10px 12px;
}

.diag-panel > summary {
	cursor: pointer;
	font-size: 13px;
	font-weight: 700;
	color: #0f766e;
	outline: none;
}

.diag-json {
	margin-top: 10px;
	max-height: 280px;
	overflow: auto;
	padding: 10px;
	border-radius: 8px;
	background: #f8fafc;
	border: 1px solid rgba(100, 116, 139, 0.2);
	font-size: 12px;
	line-height: 1.55;
	color: #1e293b;
	white-space: pre-wrap;
	word-break: break-word;
}

.chart-showcase {
	padding: 20px 18px;
	display: flex;
	flex-direction: column;
	gap: 14px;
	width: 100%;
}

.chart-chip-list {
	display: flex;
	flex-wrap: wrap;
	gap: 10px;
}

.chart-chip {
	font-size: 13px;
	font-weight: 700;
	color: #0f766e;
	background: rgba(255, 255, 255, 0.96);
	border: 1px solid rgba(15, 118, 110, 0.2);
	border-radius: 999px;
	padding: 6px 12px;
}

.chart-grid-board {
	display: grid;
	grid-template-columns: repeat(12, minmax(0, 1fr));
	gap: 16px;
	width: 100%;
}

.chart-tile {
	grid-column: span 4;
	background: linear-gradient(180deg, #ffffff 0%, #f9fcff 100%);
	border: 1px solid rgba(15, 118, 110, 0.16);
	border-radius: 14px;
	padding: 16px;
	box-shadow: 0 10px 24px rgba(15, 64, 53, 0.09);
	min-height: 280px;
}

.chart-tile.span-8 {
	grid-column: span 8;
}

.chart-tile.span-6 {
	grid-column: span 6;
}

.chart-tile.span-4 {
	grid-column: span 4;
}

.chart-tile.span-12 {
	grid-column: span 12;
}

.tile-title {
	font-size: 18px;
	font-weight: 700;
	color: #0f766e;
	letter-spacing: 0.01em;
	margin-bottom: 12px;
}

.chart-canvas {
	height: 320px;
	width: 100%;
}

.chart-tile.span-4 .chart-canvas {
	height: 320px;
}

.chart-tile.span-8 .chart-canvas {
	height: 360px;
}

.chart-tile.span-12 .chart-canvas {
	height: 380px;
}

/* 空状态 */
.empty-state {
	display: flex;
	flex-direction: column;
	align-items: center;
	justify-content: center;
	padding: 60px 20px;
	text-align: center;
	color: var(--tech-text-tertiary);

	.empty-icon {
		font-size: 64px;
		margin-bottom: 16px;
		opacity: 0.6;
	}

	.empty-text {
		font-size: 16px;
		margin: 0;
	}
}

/* 响应式设计 */
@media (max-width: 768px) {
	.behavior-view {
		padding: 16px !important;
		gap: 16px;
	}

	.control-bar {
		grid-template-columns: 1fr;
		gap: 12px;
		padding: 16px;
	}

	.button-bar {
		flex-direction: column;
		gap: 10px;
		padding: 12px;

		.action-button,
		.secondary-button {
			width: 100%;
		}

		.json-path-input {
			width: 100%;
		}
	}

	.upload-content {
		min-height: 260px;
	}

	.stats-grid {
		grid-template-columns: repeat(2, 1fr);
	}
}

/* 动画和过渡 */
@keyframes slideUp {
	from {
		opacity: 0;
		transform: translateY(12px);
	}
	to {
		opacity: 1;
		transform: translateY(0);
	}
}

.result-card {
	animation: slideUp var(--tech-transition-base) ease-out;
}
</style>
<style scoped lang="scss">
.behavior-container {
	position: relative;
}

.behavior-view {
	gap: 22px !important;
	padding: 28px !important;
	background:
		radial-gradient(circle at top left, rgba(34, 197, 94, 0.12), transparent 24%),
		radial-gradient(circle at top right, rgba(14, 165, 233, 0.12), transparent 22%),
		linear-gradient(180deg, #f8fcfa 0%, #fdfefd 100%) !important;
	position: relative;
}

.behavior-view::before {
	content: '';
	position: absolute;
	inset: 0;
	background-image: linear-gradient(rgba(15, 118, 110, 0.025) 1px, transparent 1px),
		linear-gradient(90deg, rgba(15, 118, 110, 0.025) 1px, transparent 1px);
	background-size: 32px 32px;
	mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.24), transparent 78%);
	pointer-events: none;
}

.behavior-view > * {
	position: relative;
	z-index: 1;
}

.control-bar,
.button-bar {
	border-radius: 20px !important;
	border: 1px solid rgba(15, 118, 110, 0.14) !important;
	box-shadow: var(--tech-shadow-md) !important;
	backdrop-filter: blur(10px);
}

.control-bar {
	grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)) !important;
	gap: 18px !important;
	padding: 22px !important;
	background: linear-gradient(145deg, rgba(255, 255, 255, 0.94), rgba(243, 250, 246, 0.94)) !important;
}

.control-group {
	gap: 10px !important;
	padding: 16px 18px;
	background: rgba(255, 255, 255, 0.82);
	border: 1px solid rgba(15, 118, 110, 0.1);
	border-radius: 16px;
	box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
}

.control-group .control-label {
	font-size: 12px !important;
	font-weight: 700 !important;
	color: var(--tech-text-secondary) !important;
	letter-spacing: 0.12em !important;
}

.slider-wrapper {
	gap: 14px !important;
}

.slider-wrapper .slider-value {
	min-width: 58px !important;
	padding: 8px 10px;
	border-radius: 999px;
	font-weight: 800 !important;
	font-size: 13px !important;
	background: linear-gradient(120deg, rgba(15, 118, 110, 0.1), rgba(14, 165, 233, 0.1));
}

.button-bar {
	padding: 18px 20px !important;
	background: rgba(255, 255, 255, 0.92) !important;
}

.button-bar .action-button {
	min-width: 150px !important;
	font-weight: 700 !important;
	letter-spacing: 0.04em !important;
}

.button-bar .secondary-button {
	background: rgba(255, 255, 255, 0.86) !important;
	border: 1px solid rgba(15, 118, 110, 0.2) !important;
}

.button-bar .secondary-button:hover:not(:disabled) {
	background: #ffffff !important;
	border-color: rgba(15, 118, 110, 0.48) !important;
}

.button-bar .secondary-button:disabled {
	opacity: 0.46 !important;
}

.button-bar .json-path-input {
	min-width: 220px !important;
}

.upload-file-tag {
	font-weight: 700 !important;
	letter-spacing: 0.03em !important;
	border-radius: 999px !important;
	padding: 0 14px;
}

.upload-trigger-button {
	font-weight: 700 !important;
	letter-spacing: 0.04em !important;
}

.result-card {
	border: 1px solid rgba(15, 118, 110, 0.12) !important;
	border-radius: 20px !important;
	background: rgba(255, 255, 255, 0.92) !important;
	backdrop-filter: blur(8px);
	animation: behavior-slide-up 0.45s ease-out;
}

.result-card:hover {
	border-color: rgba(15, 118, 110, 0.24) !important;
	transform: translateY(-3px);
}

.result-card :deep(.el-card__header) {
	background: linear-gradient(135deg, rgba(15, 118, 110, 0.12) 0%, rgba(14, 165, 233, 0.1) 100%) !important;
	padding: 18px 20px !important;
}

.result-card :deep(.el-card__body) {
	padding: 22px !important;
}

.result-header {
	font-weight: 800 !important;
	letter-spacing: 0.04em !important;
}

.stats-grid {
	display: flex !important;
	flex-direction: column !important;
	gap: 0 !important;
	border: 1px solid rgba(15, 118, 110, 0.14) !important;
	border-radius: 14px !important;
	overflow: hidden !important;
	background: #ffffff !important;
}

.stat-item {
	align-items: center !important;
	justify-content: space-between !important;
	min-height: 0;
	padding: 12px 14px !important;
	background: #ffffff !important;
	border-radius: 0 !important;
	border: none !important;
	border-bottom: 1px solid rgba(15, 118, 110, 0.1) !important;
	box-shadow: none !important;
}

.stat-item:hover {
	transform: none !important;
	box-shadow: none !important;
}

.stat-item:last-child {
	border-bottom: none !important;
}

.stat-item .stat-label {
	font-size: 14px !important;
	font-weight: 500 !important;
	letter-spacing: 0 !important;
	margin-bottom: 0 !important;
}

.stat-item .stat-value {
	font-size: 18px !important;
	font-weight: 800 !important;
	align-self: auto !important;
}

.markdown-content {
	line-height: 1.84 !important;
	font-family: 'IBM Plex Mono', 'Consolas', monospace !important;
	padding: 6px 2px 6px 0 !important;
}

.markdown-content :deep(code) {
	background: linear-gradient(120deg, rgba(15, 118, 110, 0.08), rgba(14, 165, 233, 0.08)) !important;
	padding: 2px 8px !important;
	border-radius: 999px !important;
	font-weight: 700 !important;
}

.image-container {
	display: block !important;
	width: 100% !important;
	background: linear-gradient(160deg, #f5fbf8 0%, #edf8fc 100%) !important;
	border-radius: 18px !important;
	min-height: 220px !important;
	border: 1px solid rgba(15, 118, 110, 0.1);
	padding: 14px !important;
	overflow: visible !important;
}

.chart-showcase {
	width: 100% !important;
	padding: 12px !important;
}

.chart-grid-board {
	width: 100% !important;
	grid-template-columns: repeat(12, minmax(0, 1fr)) !important;
	gap: 16px !important;
}

.chart-tile {
	min-height: 320px !important;
}

.tile-title {
	font-size: 18px !important;
	color: #0f766e !important;
}

.chart-canvas {
	height: 320px !important;
}

.chart-tile.span-8 .chart-canvas {
	height: 360px !important;
}

.chart-tile.span-12 .chart-canvas {
	height: 380px !important;
}

.result-image {
	max-height: 620px !important;
	border-radius: 12px !important;
}

.preview-image-wrap {
	min-height: 280px !important;
	border-radius: 14px !important;
	background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(240, 251, 247, 0.96)) !important;
}

.preview-image-lg {
	max-height: 440px !important;
}

.json-result {
	max-height: 620px !important;
	padding: 16px !important;
	border-radius: 12px !important;
	background: rgba(255, 255, 255, 0.9) !important;
	border: 1px solid rgba(15, 118, 110, 0.18) !important;
}

.diag-panel {
	margin-top: 12px !important;
	border-color: rgba(15, 118, 110, 0.28) !important;
	background: rgba(255, 255, 255, 0.82) !important;
}

.diag-json {
	max-height: 300px !important;
	background: rgba(248, 250, 252, 0.96) !important;
}

.empty-state {
	min-height: 340px;
	padding: 72px 20px !important;
	border: 1px dashed rgba(15, 118, 110, 0.26);
	border-radius: 24px;
	background: linear-gradient(180deg, rgba(255, 255, 255, 0.82), rgba(239, 252, 249, 0.86));
	backdrop-filter: blur(8px);
}

.empty-state .empty-icon {
	font-size: 68px !important;
	margin-bottom: 18px !important;
	opacity: 0.75 !important;
}

.empty-state .empty-text {
	font-weight: 700;
}

@media (max-width: 768px) {
	.behavior-view {
		padding: 16px !important;
		gap: 16px !important;
	}

	.control-bar {
		grid-template-columns: 1fr !important;
		gap: 12px !important;
		padding: 16px !important;
	}

	.button-bar {
		flex-direction: column !important;
		padding: 12px !important;
	}

	.button-bar .action-button,
	.button-bar .secondary-button,
	.button-bar .json-path-input {
		width: 100% !important;
	}

	.chart-grid-board {
		grid-template-columns: 1fr !important;
	}

	.chart-tile,
	.chart-tile.span-8,
	.chart-tile.span-6,
	.chart-tile.span-4,
	.chart-tile.span-12 {
		grid-column: 1 / -1 !important;
	}

	.chart-canvas,
	.chart-tile.span-4 .chart-canvas {
		height: 260px !important;
	}

	.chart-tile.span-8 .chart-canvas,
	.chart-tile.span-12 .chart-canvas {
		height: 300px !important;
	}

	.stats-grid {
		grid-template-columns: repeat(2, 1fr) !important;
	}

	.stat-item {
		min-height: 96px;
	}
}

@keyframes behavior-slide-up {
	from {
		opacity: 0;
		transform: translateY(18px);
	}

	to {
		opacity: 1;
		transform: translateY(0);
	}
}
</style>



