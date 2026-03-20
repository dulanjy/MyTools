<template>
	<div class="login-container">
		<div class="login-box animate__animated animate__fadeIn">
			<div class="title">
				<h2>YOLOv11 Student Behavior Detection</h2>
				<p>Sign in to continue</p>
			</div>

			<el-form :model="ruleForm" :rules="registerRules" ref="ruleFormRef">
				<el-form-item prop="username">
					<el-input v-model="ruleForm.username" placeholder="Username" prefix-icon="User" class="custom-input" />
				</el-form-item>

				<el-form-item prop="password">
					<el-input v-model="ruleForm.password" type="password" placeholder="Password" prefix-icon="Lock" show-password class="custom-input" />
				</el-form-item>

				<el-form-item>
					<el-button type="primary" class="login-btn" @click="submitForm(ruleFormRef)">Sign In</el-button>
				</el-form-item>
			</el-form>

			<div class="options">
				<router-link to="/register">Create account</router-link>
			</div>
		</div>
	</div>
</template>

<script lang="ts" setup>
import { reactive, computed, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { useI18n } from 'vue-i18n';
import Cookies from 'js-cookie';
import { storeToRefs } from 'pinia';
import { useThemeConfig } from '/@/stores/themeConfig';
import { initFrontEndControlRoutes } from '/@/router/frontEnd';
import { initBackEndControlRoutes } from '/@/router/backEnd';
import { Session } from '/@/utils/storage';
import { formatAxis } from '/@/utils/formatTime';
import { NextLoading } from '/@/utils/loading';
import type { FormInstance, FormRules } from 'element-plus';
import request from '/@/utils/request';

const { t } = useI18n();
const storesThemeConfig = useThemeConfig();
const { themeConfig } = storeToRefs(storesThemeConfig);
const route = useRoute();
const router = useRouter();
const ruleFormRef = ref<FormInstance>();

const ruleForm = reactive({
	username: '',
	password: '',
});

const registerRules = reactive<FormRules>({
	username: [
		{ required: true, message: 'Please enter username', trigger: 'blur' },
		{ min: 3, max: 20, message: 'Username must be 3-20 chars', trigger: 'blur' },
	],
	password: [
		{ required: true, message: 'Please enter password', trigger: 'blur' },
		{ min: 3, max: 20, message: 'Password must be 3-20 chars', trigger: 'blur' },
	],
});

const currentTime = computed(() => formatAxis(new Date()));

const onSignIn = async (token: string, userName: string) => {
	Session.set('token', token);
	Cookies.set('userName', userName);

	if (!themeConfig.value.isRequestRoutes) {
		const isNoPower = await initFrontEndControlRoutes();
		signInSuccess(isNoPower);
	} else {
		const isNoPower = await initBackEndControlRoutes();
		signInSuccess(isNoPower);
	}
};

const signInSuccess = (isNoPower: boolean | undefined) => {
	if (isNoPower) {
		ElMessage.warning('No permission for this account');
		Session.clear();
		return;
	}

	const signInText = t('message.signInText');
	ElMessage.success(`${currentTime.value}, ${signInText}`);
	if (route.query?.redirect) {
		let redirectQuery: Record<string, any> | '' = '';
		const params = route.query?.params;
		if (typeof params === 'string' && params) {
			try {
				redirectQuery = JSON.parse(params);
			} catch (e) {
				redirectQuery = '';
			}
		}
		router.push({
			path: String(route.query?.redirect),
			query: redirectQuery,
		});
	} else {
		router.push('/');
	}
	NextLoading.start();
};

const submitForm = (formEl: FormInstance | undefined) => {
	if (!formEl) return;
	formEl.validate((valid) => {
		if (!valid) return;

		request.post('/api/user/login', ruleForm).then((res) => {
			if (res.code === 0) {
				const loginData = res.data || {};
				const token = loginData.token;
				const user = loginData.user || {};
				const role = user.role || '';
				const userName = user.username || ruleForm.username;

				if (!token) {
					ElMessage.error('Missing token in login response');
					return;
				}

				Cookies.set('role', role);
				onSignIn(token, userName);
			} else {
				ElMessage.error(res.msg || 'Login failed');
			}
		});
	});
};
</script>

<style scoped>
.login-container {
	min-height: 100vh;
	display: flex;
	align-items: center;
	justify-content: center;
	background: linear-gradient(135deg, #56ccf2 0%, #2f80ed 100%);
	padding: 20px;
}

.login-box {
	width: 460px;
	padding: 40px 50px;
	background: rgba(255, 255, 255, 0.96);
	border-radius: 16px;
	box-shadow: 0 15px 35px rgba(0, 0, 0, 0.2);
}

.title {
	text-align: center;
	margin-bottom: 30px;
}

.title h2 {
	font-size: 22px;
	color: #2c3e50;
	margin-bottom: 8px;
}

.title p {
	font-size: 13px;
	color: #7f8c8d;
}

:deep(.custom-input .el-input__wrapper) {
	box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
	border-radius: 8px;
	padding: 12px 15px;
	background: #f8fafc;
}

.login-btn {
	width: 100%;
	padding: 12px 0;
	font-size: 16px;
	font-weight: 500;
	border-radius: 8px;
	background: linear-gradient(to right, #2f80ed 0%, #56ccf2 100%);
	border: none;
}

.options {
	margin-top: 20px;
	text-align: center;
}

.options a {
	color: #2f80ed;
	text-decoration: none;
}

@media (max-width: 768px) {
	.login-box {
		width: 90%;
		padding: 30px 20px;
	}
}
</style>
