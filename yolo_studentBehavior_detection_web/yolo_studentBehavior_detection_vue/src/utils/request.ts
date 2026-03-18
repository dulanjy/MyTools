import axios, { AxiosInstance, AxiosRequestConfig } from 'axios';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Session } from '/@/utils/storage';

const service: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_DOMAIN,
  timeout: 50000,
  headers: { 'Content-Type': 'application/json;charset=UTF-8' },
});

service.interceptors.request.use(
  (config: AxiosRequestConfig) => {
    if (Session.get('token')) {
      config.headers!['Authorization'] = `${Session.get('token')}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

service.interceptors.response.use(
  (response) => {
    const res = response.data;
    if (res.code === 401 || res.code === 4001) {
      Session.clear();
      window.location.href = '/';
      ElMessageBox.alert('你已被登出，请重新登录', '提示', {})
        .then(() => {})
        .catch(() => {});
      return;
    }
    return response.data;
  },
  (error) => {
    if (error.message?.includes('timeout')) {
      ElMessage.error('网络超时');
    } else if (error.message === 'Network Error') {
      ElMessage.error('网络连接错误');
    } else {
      const message =
        error?.response?.data?.msg ||
        error?.response?.data?.message ||
        error?.response?.statusText ||
        error?.message ||
        '接口请求失败';
      ElMessage.error(message);
    }
    return Promise.reject(error);
  }
);

export default service;