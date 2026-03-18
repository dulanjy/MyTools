<template>
  <div class="login-container">
    <div class="login-box animate__animated animate__fadeIn">
      <div class="title">
        <h2>基于 YOLOv11 的智能检测系统</h2>
        <p>YOLOV11-based Crop Disease and Pest Detection System</p>
      </div>

      <el-form ref="ruleFormRef" :model="ruleForm" :rules="registerRules">
        <el-form-item prop="username">
          <el-input v-model="ruleForm.username" placeholder="请输入用户名" prefix-icon="User" class="custom-input" />
        </el-form-item>

        <el-form-item prop="password">
          <el-input
            v-model="ruleForm.password"
            type="password"
            placeholder="请输入密码"
            prefix-icon="Lock"
            show-password
            class="custom-input"
          />
        </el-form-item>

        <el-form-item prop="confirm">
          <el-input
            v-model="ruleForm.confirm"
            type="password"
            placeholder="请确认密码"
            prefix-icon="Lock"
            show-password
            class="custom-input"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" class="login-btn" @click="submitForm(ruleFormRef)">注册</el-button>
        </el-form-item>
      </el-form>

      <div class="options">
        <router-link to="/login">已有账号？登录</router-link>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import type { FormInstance, FormRules } from 'element-plus';
import request from '/@/utils/request';

const router = useRouter();
const ruleFormRef = ref<FormInstance>();

const ruleForm = reactive({
  username: '',
  password: '',
  confirm: '',
});

const registerRules = reactive<FormRules>({
  username: [
    { required: true, message: '请输入账号', trigger: 'blur' },
    { min: 3, max: 20, message: '长度在 3-20 个字符', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 3, max: 20, message: '长度在 3-20 个字符', trigger: 'blur' },
  ],
  confirm: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value !== ruleForm.password) {
          callback(new Error('两次密码不一致'));
        } else {
          callback();
        }
      },
      trigger: 'blur',
    },
  ],
});

const submitForm = (formEl: FormInstance | undefined) => {
  if (!formEl) return;
  formEl.validate((valid) => {
    if (!valid) return;

    const payload = { username: ruleForm.username, password: ruleForm.password };
    request
      .post('/api/user/register', payload)
      .then((res) => {
        if (res.code == 0) {
          router.push('/login');
          ElMessage.success('注册成功');
        } else {
          ElMessage.error(res.msg || '用户名已存在');
        }
      })
      .catch((err) => {
        const message = err?.response?.data?.msg || err?.response?.data?.message || err?.message || '注册失败，请检查后端与数据库配置';
        ElMessage.error(message);
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
  padding: 40px;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 16px;
  box-shadow: 0 15px 35px rgba(0, 0, 0, 0.2);
}

.title {
  text-align: center;
  margin-bottom: 30px;
}

.title h2 {
  font-size: 20px;
  color: #2c3e50;
  margin-bottom: 8px;
  font-weight: 600;
}

.title p {
  font-size: 11px;
  color: #7f8c8d;
  letter-spacing: 0.5px;
}

:deep(.custom-input .el-input__wrapper) {
  border-radius: 8px;
  padding: 12px 15px;
  background: #f8fafc;
}

.login-btn {
  width: 100%;
  padding: 12px 0;
  font-size: 16px;
  border-radius: 8px;
}

.options {
  margin-top: 20px;
  text-align: center;
}

.options a {
  color: #2f80ed;
  text-decoration: none;
}
</style>