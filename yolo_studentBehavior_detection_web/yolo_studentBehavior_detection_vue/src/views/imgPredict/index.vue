<template>
	<div class="system-predict-container layout-padding">
		<div class="system-predict-padding layout-padding-auto layout-padding-view predict-view">
			<div class="control-panel">
				<div class="control-group">
					<label class="control-label">Detection Type</label>
					<el-select
						v-model="kind"
						placeholder="Select detection type"
						size="large"
						@change="getData"
						class="control-select"
					>
						<el-option v-for="item in state.kind_items" :key="item.value" :label="item.label" :value="item.value" />
					</el-select>
				</div>
				<div class="control-group">
					<label class="control-label">Model</label>
					<el-select
						v-model="weight"
						placeholder="Select model"
						size="large"
						@change="onWeightChange"
						class="control-select"
					>
						<el-option v-for="item in state.weight_items" :key="item.value" :label="item.label" :value="item.value" />
					</el-select>
				</div>
				<div class="control-group">
					<label class="control-label">Confidence Threshold</label>
					<div class="slider-wrapper">
						<el-slider v-model="conf" :format-tooltip="formatTooltip" class="control-slider" />
						<span class="slider-value">{{ (conf / 100).toFixed(2) }}</span>
					</div>
				</div>
				<el-button type="primary" @click="upData" :loading="isLoading" class="predict-button">
					<span>Run Detection</span>
				</el-button>
			</div>

			<div class="content-area">
				<div class="upload-section">
					<el-card shadow="hover" class="upload-card">
						<el-upload
							v-model="state.img"
							ref="uploadFile"
							class="avatar-uploader"
							action="/api/files/upload"
							:show-file-list="false"
							:on-success="handleAvatarSuccessone"
						>
							<div class="upload-content">
								<img v-if="imageUrl" :src="imageUrl" class="preview-image" />
								<div v-else class="upload-placeholder">
									<el-icon class="upload-icon">
										<Plus />
									</el-icon>
									<p class="upload-text">Click to upload image</p>
									<p class="upload-hint">Supports JPG / PNG</p>
								</div>
							</div>
						</el-upload>
					</el-card>
				</div>

				<div class="result-section" v-if="state.predictionResult.label">
					<el-card class="result-card" shadow="hover">
						<template #header>
							<div class="result-header">
								<span>Prediction Result</span>
							</div>
						</template>
						<div class="result-content">
							<div class="result-item">
								<span class="result-label">Label</span>
								<span class="result-value">{{ state.predictionResult.label }}</span>
							</div>
							<el-divider />
							<div class="result-item">
								<span class="result-label">Confidence</span>
								<div class="confidence-bar">
									<div class="confidence-fill" :style="{ width: parseFloat(state.predictionResult.confidence) + '%' }"></div>
									<span class="confidence-text">{{ state.predictionResult.confidence }}</span>
								</div>
							</div>
							<el-divider />
							<div class="result-item">
								<span class="result-label">Elapsed Time</span>
								<span class="result-value">{{ state.predictionResult.allTime }}</span>
							</div>
						</div>
					</el-card>
				</div>

				<div class="empty-state" v-if="!state.predictionResult.label">
					<div class="empty-icon">-</div>
					<p class="empty-text">Upload an image to start detection</p>
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
import { STUDENT_KIND_ITEMS, filterWeightsByKind, inferKindFromWeight } from '/@/utils/studentBehaviorModel';

const imageUrl = ref('');
const conf = ref('');
const weight = ref('');
const kind = ref('student');
const uploadFile = ref<UploadInstance>();
const isLoading = ref(false);
const stores = useUserInfo();
const { userInfos } = storeToRefs(stores);
const state = reactive({
	weight_items: [] as any,
	kind_items: STUDENT_KIND_ITEMS,
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
			const allItems = Array.isArray(res.data?.weight_items) ? res.data.weight_items : [];
			const filtered = filterWeightsByKind(allItems, kind.value);
			state.weight_items = filtered;
			// 闂佺厧顨庢禍婊勬叏閳哄懏鐒诲璺侯儏椤忋儳绱掑Δ濠傚幐缂佹柨鐡ㄧ粙澶愵敂閸曨偆鍩嶉梻浣规緲缁夎泛鈻撻幋婢喖鍨惧畷鍥ｅ亾閻戣姤鏅柛顐ｇ箘缁夎偐鎲搁悧鍫熷碍濠⒀呭█閺屽懏寰勭€ｎ亶浠存繛鎴炴尭缁夋潙锕㈤鍫濈婵°倕瀚ㄩ埀顒€鍟粙澶愵敇閻斿壊妲梺?
			const current = String(weight.value || '').toLowerCase();
			const exists = filtered.some((it: any) => String(it.value || '').toLowerCase() === current);
			if (!exists) {
				weight.value = filtered.length ? filtered[0].value : '';
			}
			// 闂佸吋鐪归崕鎻掞耿椤撱垺鐒诲璺侯儏椤忋儲淇婇鐔蜂壕濠电偞娼欓鍥╂偖椤愶箑鍨傞悗锝呭缁€澶娒归敐鍛棞闁告埊绱曠槐鎺曠疀閺冣偓缁犳帒霉濠婂啯顥為懚鈺呮煕閵娿儺鍎旈柍褜鍓欓ˇ鎵偓姘ュ姂閺佸秶浠﹂挊澶屼户闂佸搫绉烽～澶婄暤娴ｈ倽鐔煎灳瀹曞洠鍋撻悜钘夎Е鐎广儱鐗嗗▓浼存煕閺傝濡介悽顖氱秺瀵剟顢橀悙璺虹彲婵犻潧顦介崑鍕储?kind
			if (!kind.value) {
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

				// 婵犵鈧啿鈧綊鎮?res.data.label 闂佸搫瀚烽崹浼存偤瑜忕划顓㈡晜閼愁垼娲梺鎸庣☉閼活垶宕归婊勫枂闁挎繂妫涢埀顒冨Г缁嬪鎮滃Ο缁橆啀缂?
				if (typeof res.data.label === 'string') {
					res.data.label = JSON.parse(res.data.label);
				}

				// 缂佺虎鍙庨崰鏇犳崲?res.data.label 闂佸搫瀚烽崹閬嶅汲閻旇櫣纾奸柛鏇ㄥ亝閸婄敻鏌涢幇顒傂ラ柣銊у枛閹?map
				if (Array.isArray(res.data.label)) {
					state.predictionResult.label = res.data.label.map(item => item.replace(/\\u([\dA-Fa-f]{4})/g, (_, code) =>
						String.fromCharCode(parseInt(code, 16))
					));
				} else {
					console.error("res.data.label 婵炴垶鎸哥粔闈浳ｉ幖浣告瀬闁规鍠氶惌?", res.data.label);
				}
				state.predictionResult.confidence = res.data.confidence;
				state.predictionResult.allTime = res.data.allTime;

				// 闁荤喐娲栧Λ娑樏烘繝鍥у偍闁绘棃鏀辩粋鍫ユ煟?
				if (res.data.outImg) {
					// 婵炶揪缍€濞夋洟寮妶澶婂珘鐎广儱鎳庨～銈夋煕閿濆啫濮€缂佺粯鍨垮畷鍫曟倷閸偆鏆犻梺鍝勫€瑰妯好瑰鈧幃褔宕堕鍡欏敶閻?
					imageUrl.value = res.data.outImg;
				} else {
					// 闂佸憡鐔粻鎴﹀垂椤栨稓鈹嶆繝闈涚墛濞堝矂鏌涘Ο鐓庢瀻婵炲瓨锕㈤幃褔宕堕鍡欏敶閻?
					imageUrl.value = imageUrl.value;
				}
				console.log(state.predictionResult);
			} catch (error) {
				console.error('闁荤喐鐟辩徊楣冩倵?JSON 闂佸搫鍟冲▔娑㈠吹椤撱垺鐓?', error);
			}
			ElMessage.success('检测成功');
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

/* 闂佺鐭囬崘銊у幀闂傚倸鐗勯崹鍝勵熆?*/
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

/* 闂佸憡鍔曢幊搴敊閹版澘绀?*/
.content-area {
	display: grid;
	grid-template-columns: 1fr 1fr;
	gap: 24px;
	flex: 1;
	min-height: 0;
}

/* 婵炴垶鎸搁敃锝囨閸洖绀?*/
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

/* 缂傚倷鐒﹂幐濠氭倶婢舵劕绀?*/
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

/* 缂備礁鐭佸▍锝嗘叏閹间礁绠?*/
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

/* 闂佸憡绻傜粔瀵歌姳閹绘帩鍤曢煫鍥ㄥ嚬閸熷酣鎮?*/
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


