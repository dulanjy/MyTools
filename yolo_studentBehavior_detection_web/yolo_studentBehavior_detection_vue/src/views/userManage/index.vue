<template>
	<div class="user-manage-page layout-padding">
		<div class="user-manage-panel layout-padding-auto layout-padding-view">
			<div class="toolbar mb15">
				<div class="toolbar-left">
					<el-input
						v-model="state.tableData.param.search"
						size="large"
						placeholder="请输入用户名"
						clearable
						class="search-input"
						@keyup.enter="getTableData"
					/>
					<el-button size="large" type="primary" class="action-btn" @click="getTableData">
						<el-icon><ele-Search /></el-icon>
						<span>查询</span>
					</el-button>
				</div>
				<el-button size="large" type="success" class="action-btn" @click="onOpenAddRole('add')">
					<el-icon><ele-FolderAdd /></el-icon>
					<span>新增用户</span>
				</el-button>
			</div>

			<el-table
				:data="state.tableData.data"
				v-loading="state.tableData.loading"
				row-key="id"
				class="user-table"
				style="width: 100%"
			>
				<el-table-column prop="num" label="序号" width="72" align="center" />
				<el-table-column prop="username" label="账号" min-width="120" show-overflow-tooltip />
				<el-table-column prop="password" label="密码" min-width="100" show-overflow-tooltip />
				<el-table-column prop="name" label="姓名" min-width="100" show-overflow-tooltip />
				<el-table-column prop="sex" label="性别" width="80" align="center" />
				<el-table-column prop="email" label="邮箱" min-width="170" show-overflow-tooltip />
				<el-table-column prop="tel" label="手机号" min-width="130" show-overflow-tooltip />
				<el-table-column label="角色" width="110" align="center">
					<template #default="scope">
						<el-tag round effect="light" class="role-tag">
							{{ renderRoleLabel(scope.row.role) }}
						</el-tag>
					</template>
				</el-table-column>
				<el-table-column label="头像" width="108" align="center">
					<template #default="scope">
						<div class="avatar-cell">
							<img :src="scope.row.avatar || logoMini" class="user-avatar" alt="avatar" />
						</div>
					</template>
				</el-table-column>
				<el-table-column label="操作" width="170" align="center" fixed="right">
					<template #default="scope">
						<div class="row-actions">
							<el-button type="primary" plain size="small" @click="onOpenEditRole('edit', scope.row)">编辑</el-button>
							<el-button type="danger" plain size="small" @click="onRowDel(scope.row)">删除</el-button>
						</div>
					</template>
				</el-table-column>
			</el-table>

			<el-pagination
				@size-change="onHandleSizeChange"
				@current-change="onHandleCurrentChange"
				class="mt15"
				:pager-count="5"
				:page-sizes="[10, 20, 30]"
				v-model:current-page="state.tableData.param.pageNum"
				v-model:page-size="state.tableData.param.pageSize"
				layout="total, sizes, prev, pager, next, jumper"
				background
				:total="state.tableData.total"
			/>
		</div>
		<RoleDialog ref="roleDialogRef" @refresh="getTableData()" />
	</div>
</template>

<script setup lang="ts" name="systemRole">
import { defineAsyncComponent, onMounted, reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import request from '/@/utils/request';
import logoMini from '/@/assets/logo-mini.svg';

const RoleDialog = defineAsyncComponent(() => import('./dialog.vue'));
const roleDialogRef = ref();
const isSuccess = (code: unknown) => String(code) === '0';

const state = reactive<SysRoleState>({
	tableData: {
		data: [] as any[],
		total: 0,
		loading: false,
		param: {
			search: '',
			pageNum: 1,
			pageSize: 10,
		},
	},
});

const renderRoleLabel = (role: string) => {
	if (role === 'admin') return '管理员';
	if (role === 'common') return '普通用户';
	if (role === 'others') return '其他用户';
	return role || '-';
};

const getTableData = () => {
	state.tableData.loading = true;
	request
		.get('/api/user', {
			params: state.tableData.param,
		})
		.then((res) => {
			if (isSuccess(res.code)) {
				const records = Array.isArray(res?.data?.records) ? res.data.records : [];
				const pageOffset = (state.tableData.param.pageNum - 1) * state.tableData.param.pageSize;
				state.tableData.data = records.map((item: any, index: number) => ({
					...item,
					num: pageOffset + index + 1,
				}));
				state.tableData.total = Number(res?.data?.total || 0);
			} else {
				ElMessage.error(String(res?.msg || '加载用户失败'));
			}
		})
		.catch((e) => ElMessage.error(String(e)))
		.finally(() => {
			state.tableData.loading = false;
		});
};

const onOpenAddRole = (type: string) => {
	roleDialogRef.value?.openDialog(type);
};

const onOpenEditRole = (type: string, row: any) => {
	roleDialogRef.value?.openDialog(type, { ...row });
};

const onRowDel = (row: any) => {
	ElMessageBox.confirm('此操作将永久删除该用户，是否继续？', '提示', {
		confirmButtonText: '确认',
		cancelButtonText: '取消',
		type: 'warning',
	})
		.then(() => {
			request
				.delete(`/api/user/${row.id}`)
				.then((res) => {
					if (isSuccess(res.code)) ElMessage.success('删除成功');
					else ElMessage.error(String(res?.msg || '删除失败'));
				})
				.catch((e) => ElMessage.error(String(e)))
				.finally(() => {
					getTableData();
				});
		})
		.catch(() => undefined);
};

const onHandleSizeChange = (val: number) => {
	state.tableData.param.pageSize = val;
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
.user-manage-page {
	padding: 20px;
	background:
		radial-gradient(circle at 8% 10%, rgba(14, 165, 233, 0.1), transparent 30%),
		radial-gradient(circle at 95% 90%, rgba(34, 197, 94, 0.12), transparent 30%),
		linear-gradient(180deg, #f5faf8 0%, #eef6fb 100%);
}

.user-manage-panel {
	padding: 18px;
	border: 1px solid rgba(15, 118, 110, 0.14);
	border-radius: 18px;
	background: rgba(255, 255, 255, 0.92);
	box-shadow: 0 16px 30px rgba(20, 60, 48, 0.12);
}

.toolbar {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
	padding: 12px;
	border-radius: 14px;
	background: linear-gradient(145deg, rgba(255, 255, 255, 0.95), rgba(236, 248, 242, 0.95));
	border: 1px solid rgba(15, 118, 110, 0.12);
}

.toolbar-left {
	display: flex;
	align-items: center;
	gap: 10px;
	flex: 1;
}

.search-input {
	max-width: 260px;
}

.action-btn {
	min-width: 100px;
}

.user-table {
	:deep(.el-table__header th) {
		background: linear-gradient(180deg, #eef8f4 0%, #e7f3f9 100%);
		color: #22463a;
		font-weight: 700;
	}

	:deep(.el-table__row td) {
		padding-top: 12px;
		padding-bottom: 12px;
	}

	:deep(.el-table__row:hover > td) {
		background: rgba(22, 163, 74, 0.06);
	}
}

.avatar-cell {
	display: flex;
	align-items: center;
	justify-content: center;
}

.user-avatar {
	width: 56px;
	height: 56px;
	border-radius: 12px;
	object-fit: cover;
	border: 1px solid rgba(15, 118, 110, 0.2);
	background: #f4fbf8;
}

.role-tag {
	min-width: 72px;
	justify-content: center;
}

.row-actions {
	display: flex;
	justify-content: center;
	gap: 8px;
}

@media (max-width: 900px) {
	.user-manage-page {
		padding: 12px;
	}

	.user-manage-panel {
		padding: 12px;
	}

	.toolbar {
		flex-direction: column;
		align-items: stretch;
	}

	.toolbar-left {
		width: 100%;
	}

	.search-input {
		max-width: none;
		flex: 1;
	}
}
</style>
