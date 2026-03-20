<template>
	<div class="predict-workspace layout-padding">
		<div class="workspace-inner layout-padding-auto layout-padding-view">
			<section class="work-card controls-card">
				<div class="card-title">行为分析工作台</div>
				<el-form label-position="top" class="control-form">
					<el-form-item label="行为模型">
						<el-select v-model="behaviorWeight" placeholder="请选择行为模型" size="large">
							<el-option v-for="item in behaviorWeightItems" :key="item.value" :label="item.label" :value="item.value" />
						</el-select>
					</el-form-item>
					<el-form-item label="人数模型">
						<el-select v-model="countsWeight" placeholder="请选择人数模型" size="large">
							<el-option v-for="item in countsWeightItems" :key="item.value" :label="item.label" :value="item.value" />
						</el-select>
					</el-form-item>
					<el-form-item label="置信度阈值">
						<div class="slider-row">
							<el-slider v-model="conf" :min="1" :max="99" :format-tooltip="formatTooltip" />
							<span class="slider-value">{{ (conf / 100).toFixed(2) }}</span>
						</div>
					</el-form-item>
					<el-form-item label="输入图片">
						<el-upload ref="uploadFile" class="image-upload" action="/flask/files/upload" :show-file-list="false" :on-success="handleUploadSuccess">
							<el-button class="action-btn" type="info" plain>上传图片</el-button>
						</el-upload>
						<p class="upload-path" v-if="state.uploadFileName">{{ state.uploadFileName }}</p>
						<p class="upload-path" v-if="state.inputImagePath">{{ state.inputImagePath }}</p>
					</el-form-item>
					<div class="dual-actions">
						<el-button class="action-btn" type="primary" :loading="isLoading" @click="runDual">双模型检测</el-button>
						<el-button class="action-btn" type="success" :loading="isLoading" @click="runAnalyze">AI 分析</el-button>
					</div>
					<div class="manual-options">
						<el-checkbox v-model="preferManualAnalysis" label="使用已有分析 JSON" />
						<el-input
							v-model="manualAnalysisJsonPath"
							placeholder="请输入分析 JSON 路径"
							size="large"
							clearable
							:disabled="!preferManualAnalysis"
						/>
					</div>
				</el-form>
			</section>

			<section class="work-card preview-card">
				<div class="card-title">预览与报告</div>
				<div class="preview-grid">
					<div class="frame-panel">
						<div class="frame-title">原图</div>
						<div class="frame-stage">
							<img v-if="state.inputPreview" class="frame-image" :src="state.inputPreview" />
							<div v-else class="preview-empty">
								<span class="empty-title">暂无图片</span>
								<span class="empty-sub">请先上传图片后再开始。</span>
							</div>
						</div>
					</div>
					<div class="frame-panel">
						<div class="frame-title">分析可视化</div>
						<div class="frame-stage">
							<img v-if="state.analysisImageUrl" class="frame-image" :src="state.analysisImageUrl" />
							<div v-else class="preview-empty">
								<span class="empty-title">暂无可视化图</span>
								<span class="empty-sub">运行 AI 分析后将生成可视化图片。</span>
							</div>
						</div>
					</div>
				</div>
				<div class="report-panel">
					<div class="frame-title">AI 报告</div>
					<div class="report-body">
						<pre v-if="state.analysisMarkdown" class="report-text">{{ state.analysisMarkdown }}</pre>
						<div v-else class="preview-empty report-empty">
							<span class="empty-title">暂无报告</span>
							<span class="empty-sub">运行 AI 分析后将生成 Markdown 报告。</span>
						</div>
					</div>
				</div>
			</section>

			<section class="work-card status-card">
				<div class="card-title">任务状态</div>
				<div class="status-list">
					<div class="status-item">
						<span class="status-label">用户</span>
						<span class="status-value">{{ userInfos.userName || '-' }}</span>
					</div>
					<div class="status-item">
						<span class="status-label">行为模型</span>
						<span class="status-value">{{ behaviorWeight || '-' }}</span>
					</div>
					<div class="status-item">
						<span class="status-label">人数模型</span>
						<span class="status-value">{{ countsWeight || '-' }}</span>
					</div>
					<div class="status-item">
						<span class="status-label">人数统计</span>
						<span class="status-value">{{ headCount }}</span>
					</div>
					<div class="status-item">
						<span class="status-label">状态</span>
						<span class="status-value">{{ statusText }}</span>
					</div>
					<div class="status-item">
						<span class="status-label">行为 JSON</span>
						<span class="status-value">{{ state.savedBehaviorPath || '-' }}</span>
					</div>
					<div class="status-item">
						<span class="status-label">分析 JSON</span>
						<span class="status-value">{{ state.savedAnalysisJsonPath || '-' }}</span>
					</div>
				</div>
				<div class="status-actions">
					<el-button class="action-btn" :disabled="!state.analysisMarkdown" @click="copyReport">复制报告</el-button>
					<el-button class="action-btn" :disabled="!state.analysisJson" @click="downloadJson">下载 JSON</el-button>
				</div>
				<div class="count-panel">
					<div class="frame-title">行为计数</div>
					<div class="count-grid" v-if="countEntries.length">
						<div class="count-item" v-for="item in countEntries" :key="item.label">
							<span class="count-label">{{ item.label }}</span>
							<span class="count-value">{{ item.value }}</span>
						</div>
					</div>
					<div class="count-empty" v-else>暂无双模型检测结果。</div>
				</div>
			</section>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue';
import type { UploadInstance, UploadProps } from 'element-plus';
import { ElMessage } from 'element-plus';
import request from '/@/utils/request';
import { useUserInfo } from '/@/stores/userInfo';
import { storeToRefs } from 'pinia';

type WeightItem = { value: string; label: string };

const uploadFile = ref<UploadInstance>();
const conf = ref(25);
const behaviorWeight = ref('');
const countsWeight = ref('');
const preferManualAnalysis = ref(false);
const manualAnalysisJsonPath = ref('');
const isLoading = ref(false);
const cnHeadKey = '\u4eba\u6570';

const stores = useUserInfo();
const { userInfos } = storeToRefs(stores);

const state = reactive({
	inputImagePath: '',
	inputPreview: '',
	uploadFileName: '',
	weightItems: [] as WeightItem[],
	result: null as any,
	analysisMarkdown: '',
	analysisJson: null as any,
	analysisImageUrl: '',
	savedBehaviorPath: '',
	savedAnalysisJsonPath: '',
});

const behaviorWeightItems = computed(() => {
	const filtered = state.weightItems.filter((item) => /student|behavior|best/i.test(String(item.value || '')));
	return filtered.length ? filtered : state.weightItems;
});

const countsWeightItems = computed(() => {
	const filtered = state.weightItems.filter((item) => /count|head|per_counts/i.test(String(item.value || '')));
	return filtered.length ? filtered : state.weightItems;
});

const countEntries = computed(() => {
	const counts = state.result?.counts;
	if (!counts || typeof counts !== 'object') return [];
	return Object.entries(counts).map(([label, value]) => ({
		label,
		value: Number.isFinite(Number(value)) ? Number(value) : 0,
	}));
});

const headCount = computed(() => {
	const value = state.result?.head ?? state.result?.studentCount ?? state.result?.[cnHeadKey] ?? 0;
	const parsed = Number(value);
	return Number.isFinite(parsed) ? parsed : 0;
});

const statusText = computed(() => {
	if (isLoading.value) return '运行中';
	if (state.analysisMarkdown) return '已分析';
	if (state.result) return '已检测';
	if (state.inputImagePath) return '待执行';
	return '空闲';
});

const formatTooltip = (val: number) => (val / 100).toFixed(2);

const parseMaybeJson = (value: any): any => {
	if (typeof value !== 'string') return value;
	try {
		return JSON.parse(value);
	} catch {
		return value;
	}
};

const extractPayload = (res: any): any => {
	if (res === null || res === undefined) return {};
	if (typeof res === 'string') return parseMaybeJson(res);
	if (res?.data !== undefined) {
		return parseMaybeJson(res.data);
	}
	return res;
};

const isSuccess = (res: any, payload: any): boolean => {
	if (typeof res?.code === 'number') return res.code === 0;
	const status = payload?.status ?? res?.status;
	if (typeof status === 'number') return status < 400;
	return true;
};

const extractMessage = (res: any, payload: any, fallback: string): string => {
	return String(res?.msg || res?.message || payload?.message || fallback);
};

const extractUploadUrl = (res: any, payload: any): string => {
	if (typeof payload === 'string') return payload;
	if (typeof payload?.url === 'string') return payload.url;
	if (typeof payload?.data === 'string') return payload.data;
	if (typeof res?.url === 'string') return res.url;
	if (typeof res?.data === 'string') return res.data;
	return '';
};

const revokePreviewUrl = () => {
	if (state.inputPreview && state.inputPreview.startsWith('blob:')) {
		URL.revokeObjectURL(state.inputPreview);
	}
};

const resetAnalysis = () => {
	state.analysisMarkdown = '';
	state.analysisJson = null;
	state.analysisImageUrl = '';
	state.savedAnalysisJsonPath = '';
};

const handleUploadSuccess: UploadProps['onSuccess'] = (response, file) => {
	const payload = extractPayload(response);
	const uploadedUrl = extractUploadUrl(response, payload);
	if (!uploadedUrl) {
		ElMessage.error('上传返回中未找到有效的图片地址');
		return;
	}

	revokePreviewUrl();
	state.inputImagePath = uploadedUrl;
	state.uploadFileName = file.name || '';
	state.result = null;
	state.savedBehaviorPath = '';
	resetAnalysis();

	if (file.raw) {
		state.inputPreview = URL.createObjectURL(file.raw);
	}
	ElMessage.success('上传成功');
};

const loadWeights = async () => {
	try {
		const res = await request.get('/flask/file_names');
		const payload = extractPayload(res);
		if (!isSuccess(res, payload)) {
			ElMessage.error(extractMessage(res, payload, 'Failed to load model list'));
			return;
		}

		const items = Array.isArray(payload?.weight_items)
			? payload.weight_items
			: Array.isArray(res?.weight_items)
			? res.weight_items
			: [];
		state.weightItems = items;
		if (!state.weightItems.length) {
			ElMessage.warning('权重目录中未找到可用模型');
			return;
		}

		if (!behaviorWeight.value) {
			const preferred = state.weightItems.find((item) => /student|behavior|best_student/i.test(String(item.value || '')));
			behaviorWeight.value = preferred?.value || state.weightItems[0].value;
		}
		if (!countsWeight.value) {
			const preferred = state.weightItems.find((item) => /count|head|per_counts|best_per_counts/i.test(String(item.value || '')));
			countsWeight.value = preferred?.value || state.weightItems[0].value;
		}
	} catch (error) {
		ElMessage.error(String(error));
	}
};

const detectNeedOnnx = () => {
	const behaviorOnnx = behaviorWeight.value.toLowerCase().endsWith('.onnx');
	const countsOnnx = countsWeight.value.toLowerCase().endsWith('.onnx');
	return behaviorOnnx || countsOnnx;
};

const runDualRequest = async () => {
	const payload = {
		inputImg: state.inputImagePath,
		behavior_weight: behaviorWeight.value || './weights/best_student.pt',
		counts_weight: countsWeight.value || './weights/best_per_counts.pt',
		conf: Number(conf.value) / 100,
		imgsz: 640,
		backend: detectNeedOnnx() ? 'onnxruntime' : undefined,
		save_json: true,
	};
	const res = await request.post('/flask/dualDetect', payload);
	const body = extractPayload(res);
	if (!isSuccess(res, body)) {
		throw new Error(extractMessage(res, body, '双模型检测失败'));
	}

	state.result = body;
	state.savedBehaviorPath = String(body?.saved_paths?.behavior_json || res?.saved_paths?.behavior_json || '');
	return body;
};

const applyAnalyzeResponse = (res: any, payload: any) => {
	state.analysisMarkdown = String(payload?.analysis_markdown || '');
	state.analysisJson = payload?.analysis_json || null;
	state.analysisImageUrl = String(payload?.analysis_image_url || '');
	const savePath = String(payload?.saved_analysis_json_path || '');
	if (savePath) {
		state.savedAnalysisJsonPath = savePath;
	}
};

const runAnalyzeRequest = async (payload: any) => {
	const res = await request.post('/flask/analyze', payload);
	const body = extractPayload(res);
	if (!isSuccess(res, body)) {
		throw new Error(extractMessage(res, body, 'AI 分析失败'));
	}
	applyAnalyzeResponse(res, body);
};

const runDual = async () => {
	if (!state.inputImagePath) {
		ElMessage.warning('请先上传图片');
		return;
	}
	if (!behaviorWeight.value || !countsWeight.value) {
		ElMessage.warning('请选择行为模型和人数模型');
		return;
	}

	isLoading.value = true;
	try {
		resetAnalysis();
		await runDualRequest();
		ElMessage.success('双模型检测完成');
	} catch (error: any) {
		ElMessage.error(String(error?.message || error));
	} finally {
		isLoading.value = false;
	}
};

const runAnalyze = async () => {
	if (!state.inputImagePath) {
		ElMessage.warning('请先上传图片');
		return;
	}
	if (!behaviorWeight.value || !countsWeight.value) {
		ElMessage.warning('请选择行为模型和人数模型');
		return;
	}

	isLoading.value = true;
	try {
		const title = '课堂行为分析';
		if (preferManualAnalysis.value && manualAnalysisJsonPath.value.trim()) {
			await runAnalyzeRequest({
				analysis_json_path: manualAnalysisJsonPath.value.trim(),
				title,
			});
			state.savedAnalysisJsonPath = manualAnalysisJsonPath.value.trim();
			ElMessage.success('已使用指定 JSON 完成 AI 分析');
			return;
		}

		if (state.savedAnalysisJsonPath) {
			await runAnalyzeRequest({
				analysis_json_path: state.savedAnalysisJsonPath,
				title,
			});
			ElMessage.success('已复用历史分析结果');
			return;
		}

		if (!state.savedBehaviorPath) {
			await runDualRequest();
		}
		if (!state.savedBehaviorPath) {
			throw new Error('双模型检测未生成行为 JSON 路径');
		}

		const payload: Record<string, any> = {
			two_stage: true,
			json_only: true,
			save_json_out: true,
			strict_pipeline: true,
			title,
			behavior_json_path: state.savedBehaviorPath,
		};

		const normalizedPath = state.savedBehaviorPath.replace(/\\\\/g, '/').replace(/\\/g, '/');
		const segments = normalizedPath.split('/');
		if (segments.length > 1) {
			payload.out_dir = segments.slice(0, -1).join('/');
		}
		const fileName = segments[segments.length - 1] || '';
		if (/^input_behavior\.json$/i.test(fileName)) {
			payload.out_stem = 'input_analysis';
		}

		await runAnalyzeRequest(payload);
		ElMessage.success('AI 分析完成');
	} catch (error: any) {
		ElMessage.error(String(error?.message || error));
	} finally {
		isLoading.value = false;
	}
};

const copyReport = async () => {
	if (!state.analysisMarkdown) return;
	try {
		await navigator.clipboard.writeText(state.analysisMarkdown);
		ElMessage.success('报告已复制');
	} catch {
		ElMessage.error('复制报告失败');
	}
};

const downloadJson = () => {
	if (!state.analysisJson) return;
	try {
		const blob = new Blob([JSON.stringify(state.analysisJson, null, 2)], { type: 'application/json;charset=utf-8' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = 'analysis.json';
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);
		URL.revokeObjectURL(url);
	} catch {
		ElMessage.error('下载 JSON 失败');
	}
};

onMounted(() => {
	loadWeights();
});

onBeforeUnmount(() => {
	revokePreviewUrl();
});
</script>

<style scoped lang="scss">
.predict-workspace {
	width: 100%;
	height: 100%;

	.workspace-inner {
		display: grid;
		grid-template-columns: 340px minmax(440px, 1fr) 320px;
		gap: 16px;
		height: calc(100vh - 110px);
		padding: 16px;
		background: radial-gradient(1200px 480px at 20% 0%, #eaf3ff 0%, #f8fbff 55%, #f2f6ff 100%);
	}
}

.work-card {
	background: #ffffff;
	border: 1px solid #d9e5ff;
	border-radius: 14px;
	box-shadow: 0 6px 20px rgba(17, 68, 170, 0.08);
	padding: 16px;
	display: flex;
	flex-direction: column;
	min-height: 0;
}

.card-title {
	font-family: 'Barlow Semi Condensed', 'Noto Sans SC', sans-serif;
	font-size: 16px;
	font-weight: 700;
	letter-spacing: 0.4px;
	color: #204a9b;
	margin-bottom: 12px;
}

.control-form {
	flex: 1;
	overflow: auto;

	:deep(.el-form-item__label) {
		font-size: 12px;
		font-weight: 600;
		color: #4e5f85;
		letter-spacing: 0.4px;
	}
}

.slider-row {
	display: flex;
	align-items: center;
	gap: 10px;
}

.slider-value {
	min-width: 42px;
	text-align: right;
	font-size: 13px;
	font-weight: 700;
	color: #1f6feb;
}

.image-upload {
	display: block;
}

.upload-path {
	margin: 8px 0 0;
	font-size: 12px;
	line-height: 1.4;
	color: #5f6f92;
	word-break: break-all;
}

.dual-actions {
	display: grid;
	grid-template-columns: 1fr;
	gap: 8px;
	margin-bottom: 10px;
}

.manual-options {
	display: grid;
	gap: 8px;
	padding: 10px;
	border: 1px dashed #b8cef9;
	border-radius: 10px;
	background: #f7faff;
}

.preview-card {
	padding: 14px;
}

.preview-grid {
	display: grid;
	grid-template-columns: 1fr 1fr;
	gap: 12px;
	min-height: 250px;
}

.frame-panel {
	display: flex;
	flex-direction: column;
	min-height: 0;
}

.frame-title {
	font-size: 11px;
	font-weight: 700;
	letter-spacing: 0.5px;
	color: #6d7fa5;
	text-transform: uppercase;
	margin-bottom: 6px;
}

.frame-stage {
	flex: 1;
	min-height: 0;
	background: linear-gradient(145deg, #0f1c33 0%, #1a2b4d 100%);
	border-radius: 10px;
	overflow: hidden;
	display: flex;
	align-items: center;
	justify-content: center;
}

.frame-image {
	width: 100%;
	height: 100%;
	object-fit: contain;
}

.preview-empty {
	display: flex;
	flex-direction: column;
	align-items: center;
	gap: 8px;
	color: #b6c7ea;
	text-align: center;
	padding: 10px;
}

.empty-title {
	font-size: 16px;
	font-weight: 700;
}

.empty-sub {
	font-size: 12px;
}

.report-panel {
	margin-top: 12px;
	display: flex;
	flex-direction: column;
	min-height: 0;
	flex: 1;
}

.report-body {
	border: 1px solid #dce8ff;
	border-radius: 10px;
	background: #f8fbff;
	padding: 12px;
	flex: 1;
	overflow: auto;
}

.report-empty {
	height: 100%;
}

.report-text {
	margin: 0;
	white-space: pre-wrap;
	word-break: break-word;
	font-size: 13px;
	line-height: 1.6;
	color: #20355f;
	font-family: 'IBM Plex Mono', 'Consolas', monospace;
}

.status-card {
	padding-right: 14px;
}

.status-list {
	display: flex;
	flex-direction: column;
	gap: 10px;
	overflow: auto;
}

.status-item {
	border: 1px solid #e6edff;
	border-radius: 10px;
	padding: 10px 12px;
	background: #fbfdff;
}

.status-label {
	display: block;
	font-size: 11px;
	font-weight: 700;
	color: #6d7fa5;
	text-transform: uppercase;
	letter-spacing: 0.5px;
	margin-bottom: 4px;
}

.status-value {
	font-size: 13px;
	font-weight: 600;
	color: #1f3768;
	word-break: break-all;
}

.status-actions {
	display: grid;
	grid-template-columns: 1fr;
	gap: 8px;
	margin-top: 12px;
}

.count-panel {
	margin-top: 12px;
	border: 1px solid #dce8ff;
	border-radius: 10px;
	background: #f8fbff;
	padding: 10px;
}

.count-grid {
	display: grid;
	grid-template-columns: 1fr 1fr;
	gap: 8px;
}

.count-item {
	border: 1px solid #d8e5ff;
	border-radius: 8px;
	padding: 8px 10px;
	background: #ffffff;
}

.count-label {
	display: block;
	font-size: 11px;
	font-weight: 700;
	color: #6c7ea5;
	text-transform: uppercase;
	letter-spacing: 0.4px;
}

.count-value {
	display: block;
	margin-top: 4px;
	font-size: 18px;
	font-weight: 700;
	color: #2053ad;
}

.count-empty {
	font-size: 12px;
	color: #6b7ea7;
}

.action-btn {
	width: 100%;
	font-weight: 600;
}

@media (max-width: 1360px) {
	.predict-workspace .workspace-inner {
		grid-template-columns: 300px minmax(380px, 1fr) 280px;
	}
}

@media (max-width: 1180px) {
	.preview-grid {
		grid-template-columns: 1fr;
		min-height: 360px;
	}
}

@media (max-width: 1080px) {
	.predict-workspace .workspace-inner {
		grid-template-columns: 1fr;
		height: auto;
	}

	.work-card {
		min-height: 280px;
	}

	.preview-card {
		height: 640px;
	}

	.count-grid {
		grid-template-columns: 1fr 1fr 1fr;
	}
}

@media (max-width: 720px) {
	.count-grid {
		grid-template-columns: 1fr 1fr;
	}
}
</style>
