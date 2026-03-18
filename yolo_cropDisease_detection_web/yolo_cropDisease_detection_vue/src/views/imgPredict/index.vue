<template>
	<div class="system-predict-container layout-padding">
		<div class="system-predict-padding layout-padding-auto layout-padding-view predict-view">
			<!-- 控制面板 -->
			<div class="control-panel">
				<div class="control-group">
					<label class="control-label">检测类型</label>
					<el-select 
						v-model="kind" 
						placeholder="请选择检测类型" 
						size="large" 
						@change="getData"
						class="control-select"
					>
						<el-option v-for="item in state.kind_items" :key="item.value" :label="item.label"
							:value="item.value" />
					</el-select>
				</div>
				<div class="control-group">
					<label class="control-label">模型选择</label>
					<el-select 
						v-model="weight" 
						placeholder="请选择模型" 
						size="large" 
						@change="onWeightChange"
						class="control-select"
					>
						<el-option v-for="item in state.weight_items" :key="item.value" :label="item.label"
							:value="item.value" />
					</el-select>
				</div>
				<div class="control-group">
					<label class="control-label">置信度阈值</label>
					<div class="slider-wrapper">
						<el-slider v-model="conf" :format-tooltip="formatTooltip" class="control-slider" />
						<span class="slider-value">{{ (conf / 100).toFixed(2) }}</span>
					</div>
				</div>
			<el-button type="primary" @click="upData" :loading="isLoading" class="predict-button">
				<span>🚀 开始预测</span>
			</el-button>
			</div>

			<!-- 上传和结果区 -->
			<div class="content-area">
				<!-- 左侧上传区 -->
				<div class="upload-section">
					<el-card shadow="hover" class="upload-card">
						<el-upload 
							v-model="state.img" 
							ref="uploadFile" 
							class="avatar-uploader"
							action="http://localhost:9999/files/upload" 
							:show-file-list="false"
							:on-success="handleAvatarSuccessone"
						>
							<div class="upload-content">
								<img v-if="imageUrl" :src="imageUrl" class="preview-image" />
								<div v-else class="upload-placeholder">
									<el-icon class="upload-icon">
										<Plus />
									</el-icon>
									<p class="upload-text">点击上传图片</p>
									<p class="upload-hint">支持 JPG、PNG</p>
								</div>
							</div>
						</el-upload>
					</el-card>
				</div>

				<!-- 右侧结果区 -->
				<div class="result-section" v-if="state.predictionResult.label">
					<el-card class="result-card" shadow="hover">
						<template #header>
							<div class="result-header">
								<span>✨ 预测结果</span>
							</div>
						</template>
						<div class="result-content">
							<div class="result-item">
								<span class="result-label">识别结果</span>
								<span class="result-value">{{ state.predictionResult.label }}</span>
							</div>
							<el-divider />
							<div class="result-item">
								<span class="result-label">预测概率</span>
								<div class="confidence-bar">
									<div class="confidence-fill" :style="{ width: parseFloat(state.predictionResult.confidence) + '%' }"></div>
									<span class="confidence-text">{{ state.predictionResult.confidence }}</span>
								</div>
							</div>
							<el-divider />
							<div class="result-item">
								<span class="result-label">处理耗时</span>
								<span class="result-value">{{ state.predictionResult.allTime }}</span>
							</div>
						</div>
					</el-card>
				</div>

				<!-- 空状态 -->
				<div class="empty-state" v-if="!state.predictionResult.label">
					<div class="empty-icon">🖼️</div>
					<p class="empty-text">上传图片进行预测</p>
				</div>
			</div>
		</div>
	</div>
</template>


<script setup lang="ts" name="personal">
import { reactive, ref, onMounted } from 'vue';
import type { UploadInstance, UploadProps } from 'element-plus';
import { ElMessage } from 'element-plus';
import request from '/@/utils/request';
import { Plus } from '@element-plus/icons-vue';
import { useUserInfo } from '/@/stores/userInfo';
import { storeToRefs } from 'pinia';
import { formatDate } from '/@/utils/formatTime';

const imageUrl = ref('');
const conf = ref('');
const weight = ref('');
const kind = ref('');
const uploadFile = ref<UploadInstance>();
const isLoading = ref(false);
const stores = useUserInfo();
const { userInfos } = storeToRefs(stores);
const state = reactive({
	weight_items: [] as any,
	kind_items: [
		{
			value: 'corn',
			label: '玉米',
		},
		{
			value: 'rice',
			label: '水稻',
		},
		{
			value: 'strawberry',
			label: '草莓',
		},
		{
			value: 'tomato',
			label: '西红柿',
		},
		{
			value: 'head',
			label: '人数',
		},
	],
	img: '',
	predictionResult: {
		label: '',
		confidence: '',
		allTime: '',
	},
	form: {
		username: '',
		inputImg: null as any,
		weight: '',
		conf: null as any,
		kind: '',
		startTime: ''
	},
});

const formatTooltip = (val: number) => {
	return val / 100
}

const handleAvatarSuccessone: UploadProps['onSuccess'] = (response, uploadFile) => {
	imageUrl.value = URL.createObjectURL(uploadFile.raw!);
	state.img = response.data;
};

const getData = () => {
	request.get('/api/flask/file_names').then((res) => {
		if (res.code == 0) {
			res.data = JSON.parse(res.data);
			const name = String(kind.value || '').toLowerCase();
			const keywordsByKind: Record<string, string[]> = {
				corn: ['corn', 'maize'],
				rice: ['rice', 'paddy'],
				strawberry: ['strawberry'],
				tomato: ['tomato'],
				head: ['head', 'count', 'counts'],
			};
			let filtered: any[];
			if (!name) {
				filtered = res.data.weight_items;
			} else {
				const kws = keywordsByKind[name] || [name];
				filtered = res.data.weight_items.filter((item: any) => {
					const v = String(item.value || '').toLowerCase();
					return kws.some(kw => v.includes(kw));
				});
			}
			state.weight_items = filtered;
			// 自动选择第一个匹配的模型（当当前选择不在列表中时）
			const current = String(weight.value || '').toLowerCase();
			const exists = filtered.some((it: any) => String(it.value || '').toLowerCase() === current);
			if (!exists) {
				weight.value = filtered.length ? filtered[0].value : '';
			}
			// 若未选择检测类型，但已经有了模型选择，则根据模型名自动推断并填充 kind
			if (!name) {
				const wsel = String(weight.value || '');
				if (wsel && !kind.value) {
					const inferred2 = inferKindFromWeight(wsel);
					if (inferred2) {
						kind.value = inferred2;
					}
				}
			}
		} else {
			ElMessage.error(res.msg);
		}
	});
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
}

const onWeightChange = () => {
	const inferred = inferKindFromWeight(String(weight.value || ''));
	if (inferred) {
		kind.value = inferred;
		// 注意：不要调用 getData()，否则会按 kind 过滤权重列表，可能把当前权重过滤掉
	}
};


const upData = () => {
	state.form.weight = weight.value;
	state.form.conf = (parseFloat(conf.value) / 100);
	state.form.username = userInfos.value.userName;
	state.form.inputImg = state.img;
	state.form.kind = kind.value;
	state.form.startTime = formatDate(new Date(), 'YYYY-mm-dd HH:MM:SS');
	console.log(state.form);
	isLoading.value = true;
	request.post('/api/flask/predict', state.form).then((res) => {
		if (res.code == 0) {
			try {
				res.data = JSON.parse(res.data);

				// 如果 res.data.label 是字符串，则解析为数组
				if (typeof res.data.label === 'string') {
					res.data.label = JSON.parse(res.data.label);
				}

				// 确保 res.data.label 是数组后再调用 map
				if (Array.isArray(res.data.label)) {
					state.predictionResult.label = res.data.label.map(item => item.replace(/\\u([\dA-Fa-f]{4})/g, (_, code) =>
						String.fromCharCode(parseInt(code, 16))
					));
				} else {
					console.error("res.data.label 不是数组:", res.data.label);
				}
				state.predictionResult.confidence = res.data.confidence;
				state.predictionResult.allTime = res.data.allTime;

				// 覆盖原图片
				if (res.data.outImg) {
					// 使用服务器返回的新图片路径
					imageUrl.value = res.data.outImg;
				} else {
					// 否则保留原图片路径
					imageUrl.value = imageUrl.value;
				}
				console.log(state.predictionResult);
			} catch (error) {
				console.error('解析 JSON 时出错:', error);
			}
			ElMessage.success('预测成功！');
		} else {
			ElMessage.error(res.msg);
		}
	}).catch((e) => ElMessage.error(String(e))).finally(() => {
		isLoading.value = false;
	});
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
}

.predict-view {
	padding: 24px !important;
	background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%);
	overflow-y: auto;
	display: flex;
	flex-direction: column;
	gap: 24px;
}

/* 控制面板 */
.control-panel {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)) auto;
	gap: 16px;
	align-items: flex-end;
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
		min-width: 150px;
	}

	.slider-value {
		min-width: 50px;
		font-weight: 600;
		color: var(--tech-primary);
		font-size: 14px;
		text-align: right;
	}
}

.predict-button {
	font-weight: 600;
	letter-spacing: 0.5px;
	white-space: nowrap;
	min-width: 140px;
	height: 40px;
}

/* 内容区 */
.content-area {
	display: grid;
	grid-template-columns: 1fr 1fr;
	gap: 24px;
	flex: 1;
	min-height: 0;
}

/* 上传区 */
.upload-section {
	display: flex;
	flex-direction: column;
	min-height: 400px;
}

.upload-card {
	height: 100%;
	border: 2px dashed var(--tech-border-color) !important;
	background: transparent !important;
	transition: all var(--tech-transition-base);

	&:hover {
		border-color: var(--tech-primary);
		box-shadow: 0 0 0 4px rgba(0, 102, 255, 0.1);
	}

	:deep(.el-card__body) {
		padding: 0 !important;
		height: 100%;
	}
}

.avatar-uploader {
	width: 100%;
	height: 100%;

	:deep(.el-upload) {
		width: 100%;
		height: 100%;
	}

	:deep(.el-upload-dragger) {
		width: 100%;
		height: 100%;
		padding: 0 !important;
		border: none !important;
		background: transparent !important;
	}
}

.upload-content {
	display: flex;
	align-items: center;
	justify-content: center;
	width: 100%;
	height: 100%;
	min-height: 400px;
	background: linear-gradient(135deg, var(--tech-primary-lighter) 0%, var(--tech-accent-light) 100%);
	border-radius: 8px;
	cursor: pointer;
	transition: all var(--tech-transition-base);

	&:hover {
		background: linear-gradient(135deg, #e0f2ff 0%, #e0f7ff 100%);
	}
}

.preview-image {
	max-width: 100%;
	max-height: 100%;
	object-fit: contain;
	border-radius: 8px;
	padding: 12px;
}

.upload-placeholder {
	display: flex;
	flex-direction: column;
	align-items: center;
	gap: 12px;
	color: var(--tech-primary);
	text-align: center;

	.upload-icon {
		font-size: 48px;
		opacity: 0.6;
	}

	.upload-text {
		margin: 0;
		font-size: 14px;
		font-weight: 600;
	}

	.upload-hint {
		margin: 0;
		font-size: 12px;
		color: var(--tech-text-tertiary);
		font-weight: 400;
	}
}

/* 结果区 */
.result-section {
	display: flex;
	flex-direction: column;
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

	:deep(.el-card__body) {
		padding: 20px;
	}
}

.result-content {
	display: flex;
	flex-direction: column;
	gap: 16px;
}

.result-item {
	display: flex;
	flex-direction: column;
	gap: 8px;

	.result-label {
		font-size: 12px;
		font-weight: 600;
		color: var(--tech-text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.result-value {
		font-size: 16px;
		font-weight: 700;
		color: var(--tech-primary);
		word-break: break-all;
	}
}

.confidence-bar {
	position: relative;
	width: 100%;
	height: 32px;
	background: var(--tech-bg-secondary);
	border-radius: 8px;
	border: 1px solid var(--tech-border-color);
	overflow: hidden;
	display: flex;
	align-items: center;

	.confidence-fill {
		position: absolute;
		top: 0;
		left: 0;
		height: 100%;
		background: linear-gradient(90deg, var(--tech-primary) 0%, var(--tech-accent) 100%);
		border-radius: 8px;
		transition: width var(--tech-transition-base);
	}

	.confidence-text {
		position: relative;
		z-index: 1;
		width: 100%;
		text-align: center;
		font-weight: 700;
		color: var(--tech-primary);
		font-size: 14px;
	}
}

.el-divider {
	margin: 8px 0;
}

/* 空状态 */
.empty-state {
	display: flex;
	flex-direction: column;
	align-items: center;
	justify-content: center;
	height: 400px;
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
@media (max-width: 1024px) {
	.control-panel {
		grid-template-columns: 1fr 1fr;
	}

	.content-area {
		grid-template-columns: 1fr;
	}
}

@media (max-width: 768px) {
	.predict-view {
		padding: 16px !important;
		gap: 16px;
	}

	.control-panel {
		grid-template-columns: 1fr;
		gap: 12px;
		padding: 16px;
	}

	.predict-button {
		width: 100%;
	}

	.upload-content {
		min-height: 300px;
	}
}
</style>
