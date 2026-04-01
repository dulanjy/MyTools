<template>
	<div class="system-role-container layout-padding">
		<div class="system-role-dialog-container">
			<el-card shadow="never" class="cards">
				<template #header>
					<div class="card-header">
						<h2>个人信息</h2>
					</div>
				</template>

				<el-form ref="formRef" :model="state.form" :rules="state.rules" label-width="88px">
					<section class="form-section avatar-section">
						<div class="section-title">头像</div>
						<div class="avatar-row">
							<el-form-item label="头像" prop="avatar" class="avatar-item">
								<el-upload
									ref="uploadFile"
									class="avatar-uploader"
									action="http://localhost:9999/files/upload"
									:show-file-list="false"
									:before-upload="beforeAvatarUpload"
									:on-success="handleAvatarSuccess"
								>
									<img v-if="imageUrl" :src="imageUrl" class="avatar" />
									<div v-else class="avatar-placeholder">
										<el-icon><Plus /></el-icon>
										<span>上传头像</span>
									</div>
								</el-upload>
							</el-form-item>
							<div class="avatar-tip">支持 jpg/png/webp，文件小于 2MB</div>
						</div>
					</section>

					<section class="form-section">
						<div class="section-title">基础信息</div>
						<el-row :gutter="16">
							<el-col :xs="24" :md="12" class="mb14">
								<el-form-item label="账号" prop="username">
									<el-input v-model="state.form.username" readonly class="readonly-input" />
								</el-form-item>
								<div class="field-tip">账号不可修改</div>
							</el-col>
							<el-col :xs="24" :md="12" class="mb14">
								<el-form-item label="角色" prop="role">
									<el-input v-model="state.form.role" readonly class="readonly-input" />
								</el-form-item>
								<div class="field-tip">角色由系统分配</div>
							</el-col>
							<el-col :xs="24" :md="12" class="mb14">
								<el-form-item label="密码" prop="password">
									<el-input v-model="state.form.password" show-password placeholder="请输入密码" clearable />
								</el-form-item>
							</el-col>
							<el-col :xs="24" :md="12" class="mb14">
								<el-form-item label="姓名" prop="name">
									<el-input v-model="state.form.name" placeholder="请输入姓名" clearable />
								</el-form-item>
							</el-col>
							<el-col :xs="24" :md="12" class="mb14">
								<el-form-item label="性别" prop="sex">
									<el-select v-model="state.form.sex" placeholder="请选择性别" style="width: 100%">
										<el-option label="男" value="男" />
										<el-option label="女" value="女" />
										<el-option label="保密" value="保密" />
									</el-select>
								</el-form-item>
							</el-col>
						</el-row>
					</section>

					<section class="form-section">
						<div class="section-title">联系方式</div>
						<el-row :gutter="16">
							<el-col :xs="24" :md="12" class="mb14">
								<el-form-item label="Email" prop="email">
									<el-input v-model="state.form.email" placeholder="请输入邮箱" clearable />
								</el-form-item>
							</el-col>
							<el-col :xs="24" :md="12" class="mb14">
								<el-form-item label="手机号" prop="tel">
									<el-input v-model="state.form.tel" placeholder="请输入手机号" clearable />
								</el-form-item>
							</el-col>
						</el-row>
					</section>
				</el-form>

				<div class="action-row">
					<el-button
						type="primary"
						class="confirm-button"
						:loading="submitLoading"
						:disabled="!isFormDirty || submitLoading"
						@click="upData"
					>
						{{ isFormDirty ? '保存修改' : '未修改' }}
					</el-button>
				</div>
			</el-card>
		</div>
	</div>
</template>

<script setup lang="ts" name="personal">
import { computed, onMounted, reactive, ref } from 'vue';
import Cookies from 'js-cookie';
import { ElMessage } from 'element-plus';
import type { FormInstance, FormRules, UploadInstance, UploadProps } from 'element-plus';
import { Plus } from '@element-plus/icons-vue';
import { storeToRefs } from 'pinia';
import request from '/@/utils/request';
import { Session } from '/@/utils/storage';
import { useUserInfo } from '/@/stores/userInfo';

interface PersonalForm {
	username: string;
	password: string;
	name: string;
	sex: string;
	email: string;
	tel: string;
	role: string;
	avatar: string;
}

const ROLE_LABEL_MAP: Record<string, string> = {
	admin: '管理员',
	common: '普通用户',
	others: '其他用户',
};

const ROLE_CODE_MAP: Record<string, string> = {
	管理员: 'admin',
	普通用户: 'common',
	其他用户: 'others',
};

const createEmptyForm = (): PersonalForm => ({
	username: '',
	password: '',
	name: '',
	sex: '',
	email: '',
	tel: '',
	role: '',
	avatar: '',
});

const normalizeForm = (data: Record<string, any>): PersonalForm => ({
	username: data?.username ?? '',
	password: data?.password ?? '',
	name: data?.name ?? '',
	sex: data?.sex ?? '',
	email: data?.email ?? '',
	tel: data?.tel ?? '',
	role: data?.role ?? '',
	avatar: data?.avatar ?? '',
});

const formRef = ref<FormInstance>();
const uploadFile = ref<UploadInstance>();
const imageUrl = ref('');
const submitLoading = ref(false);
const originalFormSnapshot = ref('');

const state = reactive<{
	form: PersonalForm;
	rules: FormRules<PersonalForm>;
}>({
	form: createEmptyForm(),
	rules: {
		password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
		name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
		sex: [{ required: true, message: '请选择性别', trigger: 'change' }],
		email: [
			{
				pattern: /^$|^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/,
				message: '邮箱格式不正确',
				trigger: 'blur',
			},
		],
		tel: [
			{
				pattern: /^$|^1\d{10}$/,
				message: '手机号格式不正确',
				trigger: 'blur',
			},
		],
	},
});

const stores = useUserInfo();
const { userInfos } = storeToRefs(stores);

const isSuccessCode = (code: unknown) => Number(code) === 0 || code === '0';

const getComparableForm = () => ({
	...state.form,
	avatar: imageUrl.value || state.form.avatar || '',
});

const isFormDirty = computed(() => {
	if (!originalFormSnapshot.value) return false;
	return JSON.stringify(getComparableForm()) !== originalFormSnapshot.value;
});

const captureSnapshot = () => {
	originalFormSnapshot.value = JSON.stringify(getComparableForm());
};

const resolveCurrentUserName = async () => {
	let currentUserName = userInfos.value?.userName?.trim();
	if (currentUserName) return currentUserName;

	await stores.setUserInfos();
	currentUserName = userInfos.value?.userName?.trim();
	if (currentUserName) return currentUserName;

	const sessionUser = Session.get('userInfo')?.userName;
	if (sessionUser) return String(sessionUser).trim();

	const cookieUser = Cookies.get('userName');
	if (cookieUser) return cookieUser.trim();

	return '';
};

const beforeAvatarUpload: UploadProps['beforeUpload'] = (rawFile) => {
	const isImage = ['image/jpeg', 'image/png', 'image/webp'].includes(rawFile.type);
	if (!isImage) {
		ElMessage.error('头像仅支持 jpg/png/webp 格式');
		return false;
	}
	const isLt2M = rawFile.size / 1024 / 1024 < 2;
	if (!isLt2M) {
		ElMessage.error('头像大小不能超过 2MB');
		return false;
	}
	return true;
};

const handleAvatarSuccess: UploadProps['onSuccess'] = (response: any, file) => {
	imageUrl.value = file.raw ? URL.createObjectURL(file.raw) : '';
	state.form.avatar = response?.data ?? '';
};

const getTableData = async () => {
	const currentUserName = await resolveCurrentUserName();
	if (!currentUserName) {
		ElMessage.warning('未获取到登录用户，请重新登录');
		return;
	}

	try {
		const res = await request.get(`/api/user/${currentUserName}`);
		if (isSuccessCode(res.code) && res.data) {
			const normalized = normalizeForm(res.data);
			normalized.role = ROLE_LABEL_MAP[normalized.role] ?? normalized.role;
			Object.assign(state.form, normalized);
			imageUrl.value = normalized.avatar || '';
			captureSnapshot();
			return;
		}
		ElMessage.error(res.msg || '获取个人信息失败');
	} catch {
		ElMessage.error('获取个人信息失败，请稍后重试');
	}
};

const upData = async () => {
	if (!formRef.value || !isFormDirty.value) return;

	const valid = await formRef.value.validate().catch(() => false);
	if (!valid) return;

	submitLoading.value = true;
	try {
		const payload = {
			...state.form,
			role: ROLE_CODE_MAP[state.form.role] ?? state.form.role,
			avatar: imageUrl.value || state.form.avatar,
		};
		const res = await request.post('/api/user/update', payload);
		if (isSuccessCode(res.code)) {
			ElMessage.success('个人信息已更新');
			await getTableData();
		} else {
			ElMessage.error(res.msg || '修改失败');
		}
	} catch {
		ElMessage.error('修改失败，请稍后重试');
	} finally {
		submitLoading.value = false;
	}
};

onMounted(() => {
	getTableData();
});
</script>

<style scoped lang="scss">
.system-role-container {
	display: flex;
	justify-content: center;
	padding: 12px;
	background: #f4f7fb;
}

.system-role-dialog-container {
	width: 100%;
	max-width: 920px;
}

.cards {
	border: 1px solid #dfe7f3;
	border-radius: 14px;
	background: #fff;
	box-shadow: 0 8px 24px rgba(16, 42, 67, 0.08);
	overflow: hidden;

	:deep(.el-card__header) {
		padding: 18px 24px !important;
		border-bottom: 1px solid #e5ecf6 !important;
		background: linear-gradient(90deg, #ecf8f5 0%, #eef4fe 100%);
	}

	:deep(.el-card__body) {
		padding: 18px 24px 20px !important;
	}
}

.card-header h2 {
	margin: 0;
	font-size: 32px;
	line-height: 1.2;
	font-weight: 800;
	color: #123a5f;
}

.form-section {
	padding: 14px;
	margin-bottom: 12px;
	border-radius: 12px;
	border: 1px solid #e9eef5;
	background: #fcfdff;
}

.section-title {
	position: relative;
	margin-bottom: 12px;
	padding-left: 10px;
	font-size: 14px;
	font-weight: 700;
	color: #1e4770;
}

.section-title::before {
	content: '';
	position: absolute;
	left: 0;
	top: 3px;
	width: 3px;
	height: 14px;
	border-radius: 3px;
	background: #2b8af7;
}

.mb14 {
	margin-bottom: 14px;
}

.avatar-row {
	display: flex;
	align-items: center;
	gap: 18px;
}

.avatar-item {
	margin-bottom: 0 !important;
}

.avatar-tip {
	font-size: 12px;
	color: #667a92;
}

.field-tip {
	padding-left: 88px;
	margin-top: 6px;
	font-size: 12px;
	color: #7d8fa4;
}

:deep(.el-form-item) {
	margin-bottom: 0;
}

:deep(.el-form-item__label) {
	font-weight: 600;
	color: #274c72;
}

:deep(.el-input__wrapper),
:deep(.el-select__wrapper) {
	border-radius: 10px;
	box-shadow: 0 0 0 1px #dbe5f1 inset;
	background: #fff;
	transition: box-shadow 0.2s ease;
}

:deep(.el-input__wrapper:hover),
:deep(.el-select__wrapper:hover) {
	box-shadow: 0 0 0 1px #b7c8dc inset;
}

:deep(.el-input__wrapper.is-focus),
:deep(.el-select__wrapper.is-focused) {
	box-shadow: 0 0 0 1.5px rgba(43, 138, 247, 0.65) inset;
}

:deep(.readonly-input .el-input__wrapper) {
	background: #f5f8fc;
	cursor: not-allowed;
}

.avatar-uploader :deep(.el-upload) {
	display: flex;
	align-items: center;
	justify-content: center;
	width: 112px;
	height: 112px;
	border-radius: 12px;
	border: 1px dashed #94b9df;
	background: #f3f8ff;
	cursor: pointer;
	transition: border-color 0.2s ease, transform 0.2s ease;
}

.avatar-uploader :deep(.el-upload:hover) {
	border-color: #4f99ef;
	transform: translateY(-1px);
}

.avatar {
	width: 112px;
	height: 112px;
	border-radius: 12px;
	object-fit: cover;
}

.avatar-placeholder {
	display: flex;
	flex-direction: column;
	align-items: center;
	gap: 6px;
	font-size: 12px;
	color: #3b6d9f;
}

.avatar-placeholder :deep(.el-icon) {
	font-size: 26px;
}

.action-row {
	padding-top: 4px;
}

.confirm-button {
	display: block;
	width: 220px;
	height: 42px;
	margin: 0 auto;
	border-radius: 999px;
	border: none;
	font-size: 15px;
	font-weight: 700;
	background: linear-gradient(90deg, #1ca573 0%, #2b8af7 100%);
	box-shadow: 0 8px 18px rgba(35, 126, 209, 0.25);
}

@media (max-width: 900px) {
	.field-tip {
		padding-left: 0;
	}
}

@media (max-width: 768px) {
	.system-role-container {
		padding: 8px;
	}

	.cards :deep(.el-card__header) {
		padding: 14px 14px !important;
	}

	.cards :deep(.el-card__body) {
		padding: 14px !important;
	}

	.card-header h2 {
		font-size: 28px;
	}

	.form-section {
		padding: 12px;
	}

	.avatar-row {
		flex-direction: column;
		align-items: flex-start;
		gap: 10px;
	}

	:deep(.el-form-item__label) {
		width: 72px !important;
	}

	.confirm-button {
		width: 100%;
	}
}
</style>
