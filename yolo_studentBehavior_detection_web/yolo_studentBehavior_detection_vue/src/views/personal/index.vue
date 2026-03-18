<template>
	<div class="system-role-container layout-padding">
		<div class="system-role-dialog-container">
			<el-card shadow="hover" header="个人信息" class="cards">
				<el-form ref="roleDialogFormRef" :model="state.form" size="default" label-width="100px">
					<el-row :gutter="35">
						<el-col :xs="24" :sm="24" :md="24" :lg="24" :xl="24" class="mb20">
							<el-form-item label="头像">
								<div class="imgs">
									<el-upload
										v-model="state.form.avatar"
										ref="uploadFile"
										class="avatar-uploader"
										action="/api/files/upload"
										:show-file-list="false"
										:on-success="handleAvatarSuccessone"
									>
										<img v-if="imageUrl" :src="imageUrl" class="avatar" />
										<el-icon v-else><Plus /></el-icon>
									</el-upload>
								</div>
							</el-form-item>
						</el-col>
						<el-col :xs="24" :sm="24" :md="24" :lg="24" :xl="24" class="mb20">
							<el-form-item label="账号">
								<el-input v-model="state.form.username" placeholder="请输入账号" clearable />
							</el-form-item>
						</el-col>
						<el-col :xs="24" :sm="24" :md="24" :lg="24" :xl="24" class="mb20">
							<el-form-item label="密码">
								<el-input v-model="state.form.password" placeholder="请输入密码" clearable />
							</el-form-item>
						</el-col>
						<el-col :xs="24" :sm="24" :md="24" :lg="24" :xl="24" class="mb20">
							<el-form-item label="姓名">
								<el-input v-model="state.form.name" placeholder="请输入姓名" clearable />
							</el-form-item>
						</el-col>
						<el-col :xs="24" :sm="24" :md="24" :lg="24" :xl="24" class="mb20">
							<el-form-item label="性别">
								<el-input v-model="state.form.sex" placeholder="请输入性别" clearable />
							</el-form-item>
						</el-col>
						<el-col :xs="24" :sm="24" :md="24" :lg="24" :xl="24" class="mb20">
							<el-form-item label="Email">
								<el-input v-model="state.form.email" placeholder="请输入 Email" clearable />
							</el-form-item>
						</el-col>
						<el-col :xs="24" :sm="24" :md="24" :lg="24" :xl="24" class="mb20">
							<el-form-item label="手机号">
								<el-input v-model="state.form.tel" placeholder="请输入手机号" clearable />
							</el-form-item>
						</el-col>
						<el-col :xs="24" :sm="24" :md="24" :lg="24" :xl="24" class="mb20">
							<el-form-item label="角色">
								<el-input v-model="state.form.role" disabled placeholder="角色" />
							</el-form-item>
						</el-col>
					</el-row>
				</el-form>
				<el-button type="primary" @click="upData" size="default" class="confirm-button">确认修改</el-button>
			</el-card>
		</div>
	</div>
</template>

<script setup lang="ts" name="personal">
import { reactive, ref, onMounted } from 'vue';
import type { UploadInstance, UploadProps } from 'element-plus';
import { ElMessage } from 'element-plus';
import request from '/@/utils/request';
import { useUserInfo } from '/@/stores/userInfo';
import { storeToRefs } from 'pinia';
import { Plus } from '@element-plus/icons-vue';

const imageUrl = ref('');
const uploadFile = ref<UploadInstance>();

const handleAvatarSuccessone: UploadProps['onSuccess'] = (response, uploadFile) => {
	imageUrl.value = URL.createObjectURL(uploadFile.raw!);
	state.form.avatar = response.data;
};

const state = reactive({
	form: {} as any,
});
const stores = useUserInfo();
const { userInfos } = storeToRefs(stores);

const getTableData = () => {
	request.get('/api/user/' + userInfos.value.userName).then((res) => {
		if (res.code == 0) {
			state.form = res.data;
			if (state.form['role'] == 'admin') {
				state.form['role'] = '管理员';
			} else if (state.form['role'] == 'common') {
				state.form['role'] = '普通用户';
			} else if (state.form['role'] == 'others') {
				state.form['role'] = '其他用户';
			}
			imageUrl.value = state.form.avatar;
		} else {
			ElMessage({ type: 'error', message: res.msg });
		}
	});
};

const upData = () => {
	if (state.form['role'] == '管理员') {
		state.form['role'] = 'admin';
	} else if (state.form['role'] == '普通用户') {
		state.form['role'] = 'common';
	} else if (state.form['role'] == '其他用户') {
		state.form['role'] = 'others';
	}
	request.post('/api/user/update', state.form).then((res) => {
		if (res.code == 0) {
			ElMessage.success('修改成功');
		} else {
			ElMessage({ type: 'error', message: res.msg });
		}
	});
	setTimeout(() => {
		getTableData();
	}, 200);
};

onMounted(() => {
	getTableData();
});
</script>

<style scoped lang="scss">
.system-role-container {
	display: flex;
	align-items: center;
	justify-content: center;
	background: radial-gradient(circle, #d3e3f1 0%, #ffffff 100%);
	min-height: 100vh;
	padding: 20px;
}

.system-role-dialog-container {
	width: 100%;
	max-width: 600px;
}

.cards {
	background: #ffffff;
	border-radius: 12px;
	display: flex;
	flex-direction: column;
	align-items: center;
	box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
	border: none;
	text-align: center;

	:deep(.el-card__header) {
		background-color: transparent !important;
		border-bottom: none !important;
		padding: 24px 20px 20px !important;
		text-align: center;
		width: 100%;
	}

	:deep(.el-card__body) {
		padding: 0 20px 20px 20px !important;
		width: 100%;
	}

	:deep(.el-card__title) {
		font-size: 18px;
		font-weight: 700;
		color: #212529;
		letter-spacing: 0.3px;
	}
}

.el-form {
	width: 100%;
}

.imgs {
	font-size: 28px;
	color: hsl(215, 8%, 58%);
	width: 120px;
	height: 120px;
	display: flex;
	justify-content: center;
	align-items: center;
	border: 2px dashed #e0e0e0;
	border-radius: 8px;
	cursor: pointer;
	margin-bottom: 20px;
	transition: all 0.3s ease;
	background-color: #fafafa;

	&:hover {
		border-color: #409eff;
		background-color: #f5f7fa;
	}
}

.avatar-uploader .el-upload:hover {
	border-color: #409eff;
}

.avatar {
	width: 120px;
	height: 120px;
	display: block;
	border-radius: 8px;
}

.confirm-button {
	width: 220px;
	height: 44px;
	margin-top: 24px;
	margin-bottom: 20px;
	font-weight: 600;
	font-size: 16px;
	letter-spacing: 0.5px;
	border-radius: 8px;
	background: linear-gradient(135deg, #409eff 0%, #53a8ff 100%);
	border: none;
	color: #ffffff;
	transition: all 0.3s ease;
	box-shadow: 0 4px 15px rgba(64, 158, 255, 0.3);

	&:hover {
		transform: translateY(-2px);
		box-shadow: 0 6px 20px rgba(64, 158, 255, 0.4);
	}

	&:active {
		transform: translateY(0);
		box-shadow: 0 2px 10px rgba(64, 158, 255, 0.3);
	}
}
</style>
