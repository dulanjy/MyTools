<template>
	<div class="predict-workspace layout-padding">
		<div class="workspace-inner layout-padding-auto layout-padding-view">
			<section class="work-card controls-card">
				<div class="card-title">图片检测控制台</div>
				<el-form label-position="top" class="control-form">
					<el-form-item label="检测类型">
						<el-select v-model="kind" placeholder="请选择检测类型" size="large" @change="getData">
							<el-option v-for="item in state.kind_items" :key="item.value" :label="item.label" :value="item.value" />
						</el-select>
					</el-form-item>
					<el-form-item label="检测模型">
						<el-select v-model="weight" placeholder="请选择检测模型" size="large" @change="onWeightChange">
							<el-option v-for="item in state.weight_items" :key="item.value" :label="item.label" :value="item.value" />
						</el-select>
					</el-form-item>
					<el-form-item label="置信度阈值">
						<div class="slider-row">
							<el-slider v-model="conf" :format-tooltip="formatTooltip" />
							<span class="slider-value">{{ (conf / 100).toFixed(2) }}</span>
						</div>
					</el-form-item>
					<el-form-item label="输入图片">
						<el-upload
							ref="uploadFile"
							class="image-upload"
							action="/api/files/upload"
							:show-file-list="false"
							:on-success="handleUploadSuccess"
						>
							<el-button class="action-btn" type="info" plain>上传图片</el-button>
						</el-upload>
						<p class="upload-path" v-if="state.uploadedImage">{{ state.uploadedImage }}</p>
					</el-form-item>
					<el-button class="action-btn" type="primary" :loading="isLoading" @click="upData">开始检测</el-button>
				</el-form>
			</section>

			<section class="work-card preview-card">
				<div class="card-title">结果预览</div>
				<div class="preview-grid">
					<div class="frame-panel">
						<div class="frame-title">原图</div>
						<div class="frame-stage">
							<img v-if="state.inputPreview" class="frame-image" :src="state.inputPreview" />
							<div v-else class="preview-empty">
								<span class="empty-title">暂无图片</span>
								<span class="empty-sub">请先上传一张图片。</span>
							</div>
						</div>
					</div>
					<div class="frame-panel">
						<div class="frame-title">检测结果</div>
						<div class="frame-stage">
							<img v-if="state.outputPreview" class="frame-image" :src="state.outputPreview" />
							<div v-else class="preview-empty">
								<span class="empty-title">暂无结果</span>
								<span class="empty-sub">开始检测后会显示结果图。</span>
							</div>
						</div>
					</div>
				</div>
			</section>

			<section class="work-card result-card">
				<div class="card-title">任务状态</div>
				<div class="status-list">
					<div class="status-item">
						<span class="status-label">用户</span>
						<span class="status-value">{{ userInfos.userName || '-' }}</span>
					</div>
					<div class="status-item">
						<span class="status-label">模型</span>
						<span class="status-value">{{ weight || '-' }}</span>
					</div>
					<div class="status-item">
						<span class="status-label">类型</span>
						<span class="status-value">{{ kind || '-' }}</span>
					</div>
					<div class="status-item">
						<span class="status-label">标签</span>
						<span class="status-value">{{ state.predictionResult.label || '-' }}</span>
					</div>
					<div class="status-item">
						<span class="status-label">置信度</span>
						<span class="status-value">{{ state.predictionResult.confidence || '-' }}</span>
					</div>
					<div class="status-item">
						<span class="status-label">耗时</span>
						<span class="status-value">{{ state.predictionResult.allTime || '-' }}</span>
					</div>
					<div class="status-item">
						<span class="status-label">状态</span>
						<span class="status-value">{{ statusText }}</span>
					</div>
				</div>
			</section>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import type { UploadInstance, UploadProps } from 'element-plus';
import { ElMessage } from 'element-plus';
import request from '/@/utils/request';
import { useUserInfo } from '/@/stores/userInfo';
import { storeToRefs } from 'pinia';
import { formatDate } from '/@/utils/formatTime';
import { STUDENT_KIND_ITEMS, filterWeightsByKind, inferKindFromWeight } from '/@/utils/studentBehaviorModel';

const uploadFile = ref<UploadInstance>();
const imageUrl = ref('');
const conf = ref(50);
const weight = ref('');
const kind = ref('student');
const isLoading = ref(false);

const stores = useUserInfo();
const { userInfos } = storeToRefs(stores);

const state = reactive({
	weight_items: [] as any[],
	kind_items: STUDENT_KIND_ITEMS,
	uploadedImage: '',
	inputPreview: '',
	outputPreview: '',
	predictionResult: {
		label: '',
		confidence: '',
		allTime: '',
	},
	form: {
		username: '',
		inputImg: '',
		weight: '',
		conf: 0.5,
		kind: '',
		startTime: '',
	},
});

const statusText = computed(() => {
	if (isLoading.value) return '检测中';
	if (state.predictionResult.label) return '已完成';
	return '空闲';
});

const formatTooltip = (val: number) => (val / 100).toFixed(2);

const normalizePayload = (res: any) => {
	const parseMaybeJson = (value: any) => {
		if (typeof value !== 'string') return value;
		try {
			return JSON.parse(value);
		} catch {
			return value;
		}
	};

	let payload = parseMaybeJson(res?.data ?? res ?? {});
	if (payload && typeof payload === 'object' && 'data' in payload) {
		const nested = parseMaybeJson(payload.data);
		if (nested && typeof nested === 'object') return nested;
	}
	return payload && typeof payload === 'object' ? payload : {};
};

const parseLabelList = (value: any): string[] => {
	if (Array.isArray(value)) return value.map((it) => String(it));
	if (typeof value === 'string') {
		try {
			const parsed = JSON.parse(value);
			if (Array.isArray(parsed)) return parsed.map((it) => String(it));
		} catch {
			return value ? [value] : [];
		}
		return [];
	}
	return [];
};

const parseConfidenceList = (value: any): number[] => {
	if (Array.isArray(value)) {
		return value.map((it) => Number(it)).filter((it) => Number.isFinite(it));
	}
	if (typeof value === 'string') {
		try {
			const parsed = JSON.parse(value);
			if (Array.isArray(parsed)) {
				return parsed.map((it) => Number(it)).filter((it) => Number.isFinite(it));
			}
		} catch {
			const single = Number(value);
			if (Number.isFinite(single)) return [single];
		}
	}
	return [];
};

const extractUploadedPath = (response: any): string => {
	if (!response) return '';
	if (typeof response.data === 'string') return response.data;
	if (typeof response.url === 'string') return response.url;
	if (response.data && typeof response.data === 'object') {
		if (typeof response.data.url === 'string') return response.data.url;
		if (typeof response.data.data === 'string') return response.data.data;
	}
	return '';
};

const handleUploadSuccess: UploadProps['onSuccess'] = (response, file) => {
	const uploadedPath = extractUploadedPath(response);
	if (!uploadedPath) {
		ElMessage.error('上传结果中未返回图片地址');
		return;
	}
	state.form.inputImg = uploadedPath;
	state.uploadedImage = uploadedPath;
	state.outputPreview = '';
	state.predictionResult.label = '';
	state.predictionResult.confidence = '';
	state.predictionResult.allTime = '';

	if (file.raw) {
		imageUrl.value = URL.createObjectURL(file.raw);
		state.inputPreview = imageUrl.value;
	}
	ElMessage.success('上传成功');
};

const getData = () => {
	request.get('/api/flask/file_names').then((res) => {
		if (res.code === 0) {
			const payload = normalizePayload(res);
			const allItems = Array.isArray(payload?.weight_items) ? payload.weight_items : [];
			const filtered = filterWeightsByKind(allItems, kind.value);
			state.weight_items = filtered;
			const current = String(weight.value || '').toLowerCase();
			const exists = filtered.some((it: any) => String(it.value || '').toLowerCase() === current);
			if (!exists) {
				weight.value = filtered.length ? filtered[0].value : '';
			}
			if (!kind.value) {
				const inferred2 = inferKindFromWeight(String(weight.value || ''));
				if (inferred2) kind.value = inferred2;
			}
		} else {
			ElMessage.error(res.msg || res.message || '获取模型列表失败');
		}
	});
};

const onWeightChange = () => {
	const inferred = inferKindFromWeight(String(weight.value || ''));
	if (inferred) kind.value = inferred;
};

const upData = () => {
	if (!state.form.inputImg) {
		ElMessage.warning('请先上传图片');
		return;
	}
	if (!weight.value) {
		ElMessage.warning('请选择模型');
		return;
	}

	state.form.weight = weight.value;
	state.form.conf = Number(conf.value) / 100;
	state.form.username = userInfos.value.userName;
	state.form.kind = kind.value;
	state.form.startTime = formatDate(new Date(), 'YYYY-mm-dd HH:MM:SS');

	isLoading.value = true;
	request
		.post('/api/flask/predict', state.form)
		.then((res) => {
			if (res.code !== 0) {
				ElMessage.error(res.msg || res.message || '检测失败');
				return;
			}

			const payload = normalizePayload(res);
			const labels = parseLabelList(payload?.label);
			const confValues = parseConfidenceList(payload?.confidence);
			const maxConf = confValues.length ? Math.max(...confValues) : 0;
			const confPct = maxConf <= 1 ? Math.round(maxConf * 100) : Math.round(maxConf);

			state.predictionResult.label = labels.join(', ');
			state.predictionResult.confidence = `${Math.max(0, Math.min(100, confPct))}%`;
			state.predictionResult.allTime = String(payload?.allTime || '');
			state.outputPreview = String(payload?.outImg || '');
			ElMessage.success('检测完成');
		})
		.catch((error) => {
			ElMessage.error(String(error));
		})
		.finally(() => {
			isLoading.value = false;
		});
};

onMounted(() => {
	getData();
});
</script>

<style scoped lang="scss">
.predict-workspace {
	width: 100%;
	height: 100%;

	.workspace-inner {
		display: grid;
		grid-template-columns: 320px minmax(420px, 1fr) 320px;
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

.action-btn {
	width: 100%;
	font-weight: 600;
}

.upload-path {
	margin: 8px 0 0;
	font-size: 12px;
	line-height: 1.4;
	color: #5f6f92;
	word-break: break-all;
}

.preview-card {
	padding: 14px;
}

.preview-grid {
	display: grid;
	grid-template-columns: 1fr 1fr;
	gap: 12px;
	flex: 1;
	min-height: 0;
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

.result-card {
	padding-right: 14px;
}

.status-list {
	display: flex;
	flex-direction: column;
	gap: 12px;
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
	font-size: 14px;
	font-weight: 600;
	color: #1f3768;
	word-break: break-all;
}

@media (max-width: 1360px) {
	.predict-workspace .workspace-inner {
		grid-template-columns: 280px minmax(360px, 1fr) 280px;
	}
}

@media (max-width: 1180px) {
	.preview-grid {
		grid-template-columns: 1fr;
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
		height: 520px;
	}
}
</style>
