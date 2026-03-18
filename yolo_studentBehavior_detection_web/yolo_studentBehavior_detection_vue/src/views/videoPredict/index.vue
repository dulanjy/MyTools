<template>
	<div class="system-predict-container layout-padding">
		<div class="system-predict-padding layout-padding-auto layout-padding-view">
			<div class="header">
				<el-select v-model="kind" placeholder="选择检测类型" size="large" style="width: 180px" @change="getData">
					<el-option v-for="item in state.kind_items" :key="item.value" :label="item.label" :value="item.value" />
				</el-select>
				<el-select v-model="weight" placeholder="选择模型" size="large" style="margin-left: 20px; width: 180px" @change="onWeightChange">
					<el-option v-for="item in state.weight_items" :key="item.value" :label="item.label" :value="item.value" />
				</el-select>
				<div style="margin-left: 20px; display: flex; flex-direction: row; align-items: center">
					<div style="font-size: 14px; margin-right: 20px; color: #909399">最小置信度</div>
					<el-slider v-model="conf" :format-tooltip="formatTooltip" style="width: 280px" />
				</div>
				<el-upload
					v-model="state.form.inputVideo"
					ref="uploadFile"
					class="avatar-uploader"
					action="/api/files/upload"
					:show-file-list="false"
					:on-success="handleAvatarSuccessone"
				>
					<div class="button-section" style="margin-left: 20px">
						<el-button type="info" class="predict-button">上传视频</el-button>
					</div>
				</el-upload>
				<div class="button-section" style="margin-left: 20px">
					<el-button type="primary" @click="upData" class="predict-button">开始处理</el-button>
				</div>
				<div class="demo-progress" v-if="state.isShow">
					<el-progress :text-inside="true" :stroke-width="20" :percentage="state.percentage" style="width: 380px">
						<span>{{ state.type_text }} {{ state.percentage }}%</span>
					</el-progress>
				</div>
			</div>
			<div class="cards">
				<img v-if="state.video_path" class="video" :src="state.video_path" />
			</div>
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
const conf = ref('');
const kind = ref('student');
const weight = ref('');
const flaskStreamBase = (import.meta.env.VITE_FLASK_STREAM_BASE_URL || '').replace(/\/$/, '');
const { userInfos } = storeToRefs(stores);

const state = reactive({
	weight_items: [] as any[],
	kind_items: STUDENT_KIND_ITEMS,
	video_path: '',
	type_text: '正在保存',
	percentage: 0,
	isShow: false,
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
socketService.on('message', (data: string) => {
	ElMessage.success(data);
});
socketService.on('progress', (data: string) => {
	const percent = parseInt(data);
	state.percentage = Number.isNaN(percent) ? 0 : percent;
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

const formatTooltip = (val: number) => val / 100;

const handleAvatarSuccessone: UploadProps['onSuccess'] = (response) => {
	ElMessage.success('上传成功');
	state.form.inputVideo = response.data;
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
		if (res.code == 0) {
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
	state.form.weight = weight.value;
	state.form.conf = parseFloat(conf.value || '0') / 100;
	state.form.username = userInfos.value.userName;
	state.form.kind = kind.value;
	state.form.startTime = formatDate(new Date(), 'YYYY-mm-dd HH:MM:SS');
	const queryParams = new URLSearchParams(state.form as any).toString();
	state.video_path = `${flaskStreamBase}/flask/predictVideo?${queryParams}`;
	ElMessage.success('正在加载');
};

onMounted(() => {
	getData();
});
</script>

<style scoped lang="scss">
.system-predict-container {
	width: 100%;
	height: 100%;
	display: flex;
	flex-direction: column;

	.system-predict-padding {
		padding: 15px;
		background: radial-gradient(circle, #d3e3f1 0%, #ffffff 100%);
	}
}

.header {
	width: 100%;
	display: flex;
	justify-content: flex-start;
	align-items: center;
	flex-wrap: wrap;
	gap: 8px;
}

.cards {
	width: 100%;
	height: calc(100vh - 230px);
	border-radius: 5px;
	margin-top: 15px;
	overflow: hidden;
	display: flex;
	justify-content: center;
	align-items: center;
	background: #ffffff;
}

.video {
	width: 100%;
	max-height: 100%;
	height: auto;
	object-fit: contain;
}

.button-section {
	display: flex;
	justify-content: center;
}

.predict-button {
	width: 100%;
}

.demo-progress .el-progress--line {
	margin-left: 20px;
	width: 380px;
}
</style>
