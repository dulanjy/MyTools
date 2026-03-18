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
					<span>🔍 双模型检测</span>
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
					<!-- 统计卡片 -->
					<el-col :xs="24" :sm="12" :md="8" class="result-col">
						<el-card class="result-card" shadow="hover">
							<template #header>
								<div class="result-header">
									<span>📊 检测统计</span>
								</div>
							</template>
							<div class="stats-grid">
								<div class="stat-item" v-for="(v, k) in result.counts" :key="k">
									<span class="stat-label">{{ k }}</span>
									<span class="stat-value">{{ v }}</span>
								</div>
								<div class="stat-item">
									<span class="stat-label">人数</span>
									<span class="stat-value">{{ result.head }}</span>
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

					<!-- 可视化图片 -->
					<el-col :xs="24" class="result-col" v-if="analysisImageUrl">
						<el-card class="result-card" shadow="hover">
							<template #header>
								<div class="result-header">
									<span>🎨 检测结果可视化</span>
								</div>
							</template>
							<div class="image-container">
								<img :src="analysisImageUrl" class="result-image" />
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
import { reactive, ref, onMounted, computed } from 'vue';
import type { UploadInstance, UploadProps } from 'element-plus';
import { ElMessage } from 'element-plus';
import request from '/@/utils/request';
import { Plus } from '@element-plus/icons-vue';

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
const savedBehaviorPath = ref<string>('');
const savedAnalysisJsonPath = ref<string>('');
const analysisImageUrl = ref<string>('');

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
				ElMessage.success('检测完成');
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
					analysisImageUrl.value = res.analysis_image_url || '';
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
					analysisImageUrl.value = res.analysis_image_url || '';
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
						analysisImageUrl.value = res.analysis_image_url || '';
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

onMounted(() => getWeights());
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
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
	gap: 12px;
}

.stat-item {
	display: flex;
	flex-direction: column;
	align-items: center;
	padding: 16px 12px;
	background: var(--tech-bg-secondary);
	border-radius: 8px;
	border: 1px solid var(--tech-border-color);
	transition: all var(--tech-transition-base);

	&:hover {
		border-color: var(--tech-primary);
		box-shadow: 0 0 0 3px rgba(0, 102, 255, 0.08);
		transform: translateY(-2px);
	}

	.stat-label {
		font-size: 12px;
		color: var(--tech-text-secondary);
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.5px;
		margin-bottom: 4px;
	}

	.stat-value {
		font-size: 24px;
		font-weight: 700;
		color: var(--tech-primary);
		line-height: 1;
	}
}

/* Markdown内容 */
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
	align-items: center;
	justify-content: center;
	background: var(--tech-bg-secondary);
	border-radius: 8px;
	min-height: 200px;
	overflow: hidden;
}

.result-image {
	width: 100%;
	max-height: 600px;
	object-fit: contain;
	border-radius: 8px;
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
