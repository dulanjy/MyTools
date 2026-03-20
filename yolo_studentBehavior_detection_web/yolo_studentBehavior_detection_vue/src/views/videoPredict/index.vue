<template>
	<div class="predict-workspace layout-padding">
		<div class="workspace-inner layout-padding-auto layout-padding-view">
			<section class="work-card controls-card">
				<div class="card-title">视频检测控制台</div>
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
					<el-form-item label="输入视频">
						<el-upload
							v-model="state.form.inputVideo"
							ref="uploadFile"
							class="video-upload"
							action="/api/files/upload"
							:show-file-list="false"
							:on-success="handleAvatarSuccessone"
						>
							<el-button class="action-btn" type="info" plain>上传视频</el-button>
						</el-upload>
						<p class="upload-path" v-if="state.uploadedVideo">{{ state.uploadedVideo }}</p>
					</el-form-item>
					<el-button class="action-btn" type="primary" :loading="state.isRunning" @click="upData">开始检测</el-button>
				</el-form>
			</section>

			<section class="work-card preview-card">
				<div class="card-title">视频预览</div>
				<div class="preview-stage">
					<img v-if="state.video_path" class="video" :src="state.video_path" />
					<div v-else class="preview-empty">
						<span class="empty-title">暂无视频流</span>
						<span class="empty-sub">请先上传视频并开始检测。</span>
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
						<span class="status-label">进度</span>
						<div class="progress-block">
							<el-progress :percentage="state.percentage" :stroke-width="16" :text-inside="true" />
						</div>
					</div>
					<div class="status-item">
						<span class="status-label">状态</span>
						<span class="status-value">{{ state.isShow ? `${state.type_text} ${state.percentage}%` : '空闲' }}</span>
					</div>
				</div>
			</section>
		</div>
	</div>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue';
import { ElMessage } from 'element-plus';
import request from '/@/utils/request';
import { useUserInfo } from '/@/stores/userInfo';
import { storeToRefs } from 'pinia';
import type { UploadInstance, UploadProps } from 'element-plus';
import { SocketService } from '/@/utils/socket';
import { formatDate } from '/@/utils/formatTime';
import { STUDENT_KIND_ITEMS, filterWeightsByKind, inferKindFromWeight } from '/@/utils/studentBehaviorModel';

const uploadFile = ref<UploadInstance>();
const stores = useUserInfo();
const { userInfos } = storeToRefs(stores);

const conf = ref(50);
const kind = ref('student');
const weight = ref('');
const flaskStreamBase = (import.meta.env.VITE_FLASK_STREAM_BASE_URL || '').replace(/\/$/, '');

const state = reactive({
	weight_items: [] as any[],
	kind_items: STUDENT_KIND_ITEMS,
	video_path: '',
	type_text: '处理中',
	percentage: 0,
	isShow: false,
	isRunning: false,
	uploadedVideo: '',
	form: {
		username: '',
		inputVideo: null as any,
		weight: '',
		conf: null as any,
		kind: '',
		startTime: '',
	},
});

const socketService = new SocketService();
const parseSocketText = (payload: any): string => {
	if (typeof payload === 'string') return payload;
	if (payload && typeof payload === 'object') {
		if (typeof payload.data === 'string') return payload.data;
		if (typeof payload.message === 'string') return payload.message;
	}
	return '';
};
const parseSocketPercent = (payload: any): number => {
	if (typeof payload === 'number') return Math.max(0, Math.min(100, payload));
	if (typeof payload === 'string') {
		const n = parseInt(payload, 10);
		return Number.isNaN(n) ? 0 : Math.max(0, Math.min(100, n));
	}
	if (payload && typeof payload === 'object') {
		const raw = payload.progress ?? payload.data;
		const n = parseInt(String(raw ?? ''), 10);
		return Number.isNaN(n) ? 0 : Math.max(0, Math.min(100, n));
	}
	return 0;
};
socketService.on('message', (data: any) => {
	const text = parseSocketText(data);
	if (text) {
		ElMessage.success(text);
	}
});
socketService.on('progress', (data: any) => {
	state.percentage = parseSocketPercent(data);
	if (state.percentage < 100) {
		state.isShow = true;
	} else {
		ElMessage.success('保存成功');
		setTimeout(() => {
			state.isShow = false;
			state.percentage = 0;
		}, 1200);
	}
});

const formatTooltip = (val: number) => (val / 100).toFixed(2);

const handleAvatarSuccessone: UploadProps['onSuccess'] = (response) => {
	state.form.inputVideo = response.data;
	state.uploadedVideo = response.data;
	ElMessage.success('上传成功');
};

const normalizePayload = (res: any) => {
	if (typeof res?.data === 'string') {
		try {
			return JSON.parse(res.data);
		} catch {
			return {};
		}
	}
	return res?.data || res || {};
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
	if (!state.form.inputVideo) {
		ElMessage.warning('请先上传视频');
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
	state.isRunning = true;

	const queryParams = new URLSearchParams(state.form as any).toString();
	state.video_path = `${flaskStreamBase}/flask/predictVideo?${queryParams}`;
	ElMessage.success('已开始检测');
	setTimeout(() => {
		state.isRunning = false;
	}, 600);
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

.video-upload {
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

.preview-stage {
	flex: 1;
	min-height: 0;
	background: linear-gradient(145deg, #0f1c33 0%, #1a2b4d 100%);
	border-radius: 12px;
	overflow: hidden;
	display: flex;
	align-items: center;
	justify-content: center;
}

.video {
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
}

.empty-title {
	font-size: 18px;
	font-weight: 700;
}

.empty-sub {
	font-size: 13px;
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

.progress-block {
	padding-top: 2px;
}

@media (max-width: 1360px) {
	.predict-workspace .workspace-inner {
		grid-template-columns: 280px minmax(360px, 1fr) 280px;
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
		height: 420px;
	}
}
</style>
