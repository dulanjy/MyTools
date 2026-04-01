<template>
	<div class="record-page layout-padding">
		<div class="record-panel layout-padding-auto layout-padding-view">
			<div class="stats-grid">
				<div class="stat-card">
					<div class="stat-label">记录总数</div>
					<div class="stat-value">{{ state.tableData.total }}</div>
				</div>
				<div class="stat-card">
					<div class="stat-label">当前页记录</div>
					<div class="stat-value">{{ state.tableData.data.length }}</div>
				</div>
				<div class="stat-card">
					<div class="stat-label">已选中</div>
					<div class="stat-value">{{ selectedIds.length }}</div>
				</div>
			</div>

			<div class="toolbar mb15">
				<div class="toolbar-left">
					<el-input
						v-model="state.tableData.param.search1"
						size="large"
						placeholder="检测类型"
						clearable
						class="search-input"
						@keyup.enter="onQuery"
					/>
					<el-input
						v-model="state.tableData.param.search2"
						size="large"
						placeholder="权重关键词"
						clearable
						class="search-input"
						@keyup.enter="onQuery"
					/>
					<el-input
						v-model="state.tableData.param.search3"
						size="large"
						placeholder="阈值"
						clearable
						class="search-input"
						@keyup.enter="onQuery"
					/>
					<el-input
						v-model="state.tableData.param.search"
						size="large"
						placeholder="识别用户（管理员）"
						clearable
						class="search-input"
						:disabled="!isAdmin"
						@keyup.enter="onQuery"
					/>
					<el-date-picker
						v-model="dateRange"
						type="daterange"
						size="large"
						class="date-range"
						value-format="YYYY-MM-DD HH:mm:ss"
						:shortcuts="dateShortcuts"
						range-separator="至"
						start-placeholder="开始时间"
						end-placeholder="结束时间"
						clearable
					/>
				</div>
				<div class="toolbar-right">
					<el-button size="large" type="primary" @click="onQuery">
						<el-icon><ele-Search /></el-icon>
						<span>查询</span>
					</el-button>
					<el-button size="large" @click="onReset">重置</el-button>
					<el-button size="large" @click="getTableData">刷新</el-button>
					<el-button size="large" type="danger" :disabled="!selectedIds.length" @click="onBatchDel">批量删除</el-button>
				</div>
			</div>

			<el-table
				:data="state.tableData.data"
				v-loading="state.tableData.loading"
				row-key="id"
				class="record-table"
				style="width: 100%"
				@selection-change="onSelectionChange"
			>
				<el-table-column type="selection" width="52" reserve-selection />
				<el-table-column prop="num" label="序号" width="72" align="center" />
				<el-table-column prop="inputVideo" label="原视频" min-width="220" align="center">
					<template #default="scope">
						<template v-if="scope.row.inputVideo">
							<video class="video-preview" controls preload="metadata" playsinline :key="`${scope.row.inputVideo || 'input'}-${uniqueKey}`">
								<source :src="getPlayableVideoUrl(scope.row.inputVideo)" :type="getVideoMimeType(getPlayableVideoUrl(scope.row.inputVideo))" />
								<source
									v-if="getPlayableVideoUrl(scope.row.inputVideo) !== scope.row.inputVideo"
									:src="scope.row.inputVideo"
									:type="getVideoMimeType(scope.row.inputVideo)"
								/>
							</video>
						</template>
						<span v-else>-</span>
					</template>
				</el-table-column>
				<el-table-column prop="outVideo" label="处理结果" min-width="220" align="center">
					<template #default="scope">
						<template v-if="scope.row.outVideo">
							<video class="video-preview" controls preload="metadata" playsinline :key="`${scope.row.outVideo || 'output'}-${uniqueKey}`">
								<source :src="getPlayableVideoUrl(scope.row.outVideo)" :type="getVideoMimeType(getPlayableVideoUrl(scope.row.outVideo))" />
								<source
									v-if="getPlayableVideoUrl(scope.row.outVideo) !== scope.row.outVideo"
									:src="scope.row.outVideo"
									:type="getVideoMimeType(scope.row.outVideo)"
								/>
							</video>
						</template>
						<span v-else>-</span>
					</template>
				</el-table-column>
				<el-table-column prop="kind" label="检测类型" width="110" align="center" />
				<el-table-column prop="weight" label="权重" min-width="130" show-overflow-tooltip />
				<el-table-column prop="conf" label="阈值" width="90" align="center" />
				<el-table-column prop="username" label="识别用户" width="120" align="center" />
				<el-table-column prop="startTime" label="识别时间" min-width="170" align="center" />
				<el-table-column label="操作" width="170" fixed="right" align="center">
					<template #default="scope">
						<div class="row-actions">
							<el-button size="small" type="primary" class="detail-btn" @click="show(scope.row)">详情</el-button>
							<el-button size="small" type="danger" plain @click="onRowDel(scope.row)">删除</el-button>
						</div>
					</template>
				</el-table-column>
			</el-table>

			<el-pagination
				@size-change="onHandleSizeChange"
				@current-change="onHandleCurrentChange"
				class="mt15"
				:pager-count="5"
				:page-sizes="[10, 20, 50, 100]"
				v-model:current-page="state.tableData.param.pageNum"
				v-model:page-size="state.tableData.param.pageSize"
				layout="total, sizes, prev, pager, next, jumper"
				background
				:total="state.tableData.total"
			/>
		</div>
	</div>
</template>

<script setup lang="ts" name="videoRecordPage">
import { computed, onMounted, reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import request from '/@/utils/request';
import { useUserInfo } from '/@/stores/userInfo';
import { storeToRefs } from 'pinia';

const stores = useUserInfo();
const { userInfos } = storeToRefs(stores);
const isAdmin = computed(() => userInfos.value.userName === 'admin');

const state = reactive({
	tableData: {
		data: [] as any[],
		total: 0,
		loading: false,
		param: {
			search: '',
			search1: '',
			search2: '',
			search3: '',
			startTimeFrom: '',
			startTimeTo: '',
			pageNum: 1,
			pageSize: 20,
		},
	},
});

const uniqueKey = ref(0);
const dateRange = ref<string[]>([]);
const selectedIds = ref<number[]>([]);
const isSuccess = (code: unknown) => String(code) === '0';
const getFileExt = (url: string) => {
	const clean = String(url || '').split('#')[0].split('?')[0];
	const index = clean.lastIndexOf('.');
	if (index < 0) return '';
	return clean.slice(index + 1).toLowerCase();
};

const getPlayableVideoUrl = (url: string) => {
	const raw = String(url || '').trim();
	if (!raw) return '';
	if (getFileExt(raw) !== 'avi') return raw;
	return raw.replace(/\.avi($|[?#])/i, '.mp4$1');
};

const getVideoMimeType = (url: string) => {
	switch (getFileExt(url)) {
		case 'webm':
			return 'video/webm';
		case 'ogg':
		case 'ogv':
			return 'video/ogg';
		case 'mov':
			return 'video/quicktime';
		case 'avi':
			return 'video/x-msvideo';
		case 'mkv':
			return 'video/x-matroska';
		default:
			return 'video/mp4';
	}
};

const dateShortcuts = [
	{
		text: '今天',
		value: () => {
			const now = new Date();
			const start = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0);
			const end = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59);
			return [start, end];
		},
	},
	{
		text: '昨天',
		value: () => {
			const now = new Date();
			const start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1, 0, 0, 0);
			const end = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1, 23, 59, 59);
			return [start, end];
		},
	},
	{
		text: '近7天',
		value: () => {
			const now = new Date();
			const start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 6, 0, 0, 0);
			const end = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59);
			return [start, end];
		},
	},
	{
		text: '近30天',
		value: () => {
			const now = new Date();
			const start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 29, 0, 0, 0);
			const end = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59);
			return [start, end];
		},
	},
];
const updateRangeParams = () => {
	if (dateRange.value.length === 2) {
		state.tableData.param.startTimeFrom = dateRange.value[0];
		state.tableData.param.startTimeTo = dateRange.value[1];
	} else {
		state.tableData.param.startTimeFrom = '';
		state.tableData.param.startTimeTo = '';
	}
};

const normalizeRecord = (item: any, index: number) => ({
	...item,
	id: item.id,
	num: (state.tableData.param.pageNum - 1) * state.tableData.param.pageSize + index + 1,
	inputVideo: item.inputVideo || item.input_video || '',
	outVideo: item.outVideo || item.out_video || '',
	kind: item.kind || '-',
	weight: item.weight || '-',
	conf: item.conf || '-',
	username: item.username || '-',
	startTime: item.startTime || item.start_time || '-',
});

const getTableData = () => {
	state.tableData.loading = true;
	updateRangeParams();
	if (!isAdmin.value) {
		state.tableData.param.search = userInfos.value.userName;
	}

	request
		.get('/api/videoRecords', {
			params: state.tableData.param,
		})
		.then((res) => {
			if (!isSuccess(res?.code)) {
				ElMessage.error(String(res?.msg || '查询失败'));
				state.tableData.data = [];
				state.tableData.total = 0;
				return;
			}
			const records = Array.isArray(res?.data?.records) ? res.data.records : [];
			state.tableData.data = records.map((item: any, index: number) => normalizeRecord(item, index));
			state.tableData.total = Number(res?.data?.total || 0);
			uniqueKey.value += 1;
		})
		.catch((e) => {
			ElMessage.error(String(e));
		})
		.finally(() => {
			state.tableData.loading = false;
		});
};

const onQuery = () => {
	state.tableData.param.pageNum = 1;
	getTableData();
};

const onReset = () => {
	state.tableData.param.search1 = '';
	state.tableData.param.search2 = '';
	state.tableData.param.search3 = '';
	if (isAdmin.value) state.tableData.param.search = '';
	dateRange.value = [];
	state.tableData.param.pageNum = 1;
	selectedIds.value = [];
	getTableData();
};

const onSelectionChange = (rows: any[]) => {
	selectedIds.value = rows.map((item) => Number(item.id)).filter((id) => Number.isFinite(id));
};

const deleteByIds = async (ids: number[]) => {
	try {
		const res = await request.post('/api/videoRecords/batchDelete', ids);
		if (!isSuccess(res?.code)) throw new Error(String(res?.msg || '批量删除失败'));
	} catch {
		const settled = await Promise.allSettled(ids.map((id) => request.delete(`/api/videoRecords/${id}`)));
		const failCount = settled.filter((item) => item.status === 'rejected').length;
		if (failCount > 0) {
			throw new Error(`批量删除失败，失败 ${failCount} 条`);
		}
	}
};

const onBatchDel = async () => {
	if (!selectedIds.value.length) {
		ElMessage.warning('请先选择要删除的记录');
		return;
	}
	try {
		await ElMessageBox.confirm(`确定删除选中的 ${selectedIds.value.length} 条记录吗？`, '提示', {
			confirmButtonText: '确认',
			cancelButtonText: '取消',
			type: 'warning',
		});
		const deleteCount = selectedIds.value.length;
		await deleteByIds(selectedIds.value);
		ElMessage.success('批量删除成功');
		if (deleteCount >= state.tableData.data.length && state.tableData.param.pageNum > 1) {
			state.tableData.param.pageNum -= 1;
		}
		selectedIds.value = [];
		getTableData();
	} catch (e: any) {
		if (String(e || '').includes('cancel')) return;
		ElMessage.error(String(e?.message || e));
	}
};

const onRowDel = (row: any) => {
	ElMessageBox.confirm('此操作将永久删除该记录，是否继续？', '提示', {
		confirmButtonText: '确认',
		cancelButtonText: '取消',
		type: 'warning',
	})
		.then(async () => {
			try {
				const res = await request.delete(`/api/videoRecords/${row.id}`);
				if (!isSuccess(res?.code)) {
					ElMessage.error(String(res?.msg || '删除失败'));
					return;
				}
				ElMessage.success('删除成功');
				getTableData();
			} catch (e) {
				ElMessage.error(String(e));
			}
		})
		.catch(() => undefined);
};

const show = (row: any) => {
	window.open(`http://localhost:8888/#/videoShow?id=${row.id}`);
};

const onHandleSizeChange = (val: number) => {
	state.tableData.param.pageSize = val;
	state.tableData.param.pageNum = 1;
	getTableData();
};

const onHandleCurrentChange = (val: number) => {
	state.tableData.param.pageNum = val;
	getTableData();
};

onMounted(() => {
	getTableData();
});
</script>

<style scoped lang="scss">
.record-page {
	padding: 20px;
	background:
		radial-gradient(circle at 8% 10%, rgba(14, 165, 233, 0.12), transparent 32%),
		radial-gradient(circle at 94% 88%, rgba(34, 197, 94, 0.13), transparent 34%),
		linear-gradient(180deg, #f5faf8 0%, #eef6fb 100%);
}

.record-panel {
	padding: 18px;
	border-radius: 18px;
	border: 1px solid rgba(15, 118, 110, 0.15);
	background: rgba(255, 255, 255, 0.92);
	box-shadow: 0 16px 30px rgba(20, 60, 48, 0.12);
}

.stats-grid {
	display: grid;
	grid-template-columns: repeat(3, minmax(0, 1fr));
	gap: 12px;
	margin-bottom: 14px;
}

.stat-card {
	padding: 12px 14px;
	border-radius: 14px;
	border: 1px solid rgba(15, 118, 110, 0.14);
	background: linear-gradient(145deg, rgba(255, 255, 255, 0.98), rgba(237, 249, 244, 0.9));
}

.stat-label {
	font-size: 13px;
	color: #4c695d;
}

.stat-value {
	margin-top: 6px;
	font-size: 24px;
	line-height: 1.1;
	font-weight: 700;
	color: #1f3f33;
}

.toolbar {
	display: grid;
	grid-template-columns: minmax(0, 1fr) auto;
	align-items: start;
	gap: 12px;
	padding: 12px;
	border-radius: 14px;
	background: linear-gradient(145deg, rgba(255, 255, 255, 0.95), rgba(236, 248, 242, 0.95));
	border: 1px solid rgba(15, 118, 110, 0.12);
}

.toolbar-left,
.toolbar-right {
	display: flex;
	align-items: center;
	gap: 10px;
	flex-wrap: wrap;
}

.toolbar-left {
	min-width: 0;
}

.toolbar-right {
	flex-wrap: nowrap;
	flex-shrink: 0;
}

.search-input {
	width: 150px;
}

.date-range {
	width: 340px;
}

.record-table {
	:deep(.el-table__header th) {
		background: linear-gradient(180deg, #eef8f4 0%, #e7f3f9 100%);
		color: #22463a;
		font-weight: 700;
	}

	:deep(.el-table__row td) {
		padding-top: 11px;
		padding-bottom: 11px;
	}

	:deep(.el-table__row:hover > td) {
		background: rgba(22, 163, 74, 0.06);
	}
}

.video-preview {
	width: 180px;
	height: 110px;
	border-radius: 10px;
	object-fit: cover;
	border: 1px solid rgba(15, 118, 110, 0.16);
	background: #f3faf7;
}

.row-actions {
	display: flex;
	justify-content: center;
	gap: 8px;
}

:deep(.row-actions .detail-btn.el-button) {
	border: none !important;
	background: #0f766e !important;
	background-image: none !important;
	color: #ffffff !important;
	font-weight: 600;
	box-shadow: none !important;
	-webkit-box-shadow: none !important;
	outline: none !important;
}

:deep(.row-actions .detail-btn.el-button span) {
	color: #ffffff !important;
}

:deep(.row-actions .detail-btn.el-button:hover),
:deep(.row-actions .detail-btn.el-button:focus) {
	border: none !important;
	background: #0d6660 !important;
	background-image: none !important;
	color: #ffffff !important;
	box-shadow: none !important;
	-webkit-box-shadow: none !important;
	outline: none !important;
}

@media (max-width: 1100px) {
	.record-page {
		padding: 12px;
	}

	.record-panel {
		padding: 12px;
	}

	.stats-grid {
		grid-template-columns: 1fr;
	}

	.toolbar {
		flex-direction: column;
		align-items: stretch;
	}

	.toolbar-left,
	.toolbar-right {
		width: 100%;
	}

	.search-input,
	.date-range,
	.video-preview {
		width: 100%;
	}
}
</style>


