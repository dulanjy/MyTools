<template>
  <div class="behavior-container layout-padding">
    <div class="layout-padding-auto layout-padding-view">
      <div class="header">
        <div class="weight">
          <el-select v-model="behaviorWeight" placeholder="选择行为模型" size="large" style="width: 220px">
            <el-option v-for="w in behaviorWeightItems" :key="w.value" :label="w.label" :value="w.value" />
          </el-select>
        </div>
        <div class="weight" style="margin-left: 16px">
          <el-select v-model="countsWeight" placeholder="选择人头计数模型" size="large" style="width: 240px">
            <el-option v-for="w in countsWeightItems" :key="w.value" :label="w.label" :value="w.value" />
          </el-select>
        </div>
        <div class="conf" style="margin-left: 16px; display: flex; align-items: center;">
          <span class="conf-label">置信度</span>
          <el-slider v-model="conf" :min="1" :max="99" :format-tooltip="formatTooltip" style="width: 260px" />
        </div>
        <div style="margin-left: 16px">
          <el-button type="primary" @click="runDual">双模型检测</el-button>
        </div>
        <div style="margin-left: 8px">
          <el-button @click="runAnalyze">AI 分析</el-button>
        </div>
        <div style="margin-left: 16px; display: flex; align-items: center; gap: 8px; min-width: 420px;">
          <el-checkbox v-model="preferManualAnalysis" label="使用指定AI化JSON" />
          <el-input v-model="manualAnalysisJsonPath" placeholder="本机JSON路径，例如：g:\\MyCode\\MyTools\\screen_capture\\analyze_images\\*.json" size="large" clearable style="width: 520px;" />
        </div>
        <div style="margin-left: 8px">
          <el-button :disabled="!analysisMarkdown" @click="copyReport">复制报告</el-button>
        </div>
        <div style="margin-left: 8px">
          <el-button :disabled="!analysisJson" @click="downloadJson">下载 JSON</el-button>
        </div>
      </div>

      <el-card shadow="hover" class="card">
  <el-upload v-model="state.img" ref="uploadFile" class="avatar-uploader"
       action="/flask/files/upload" :show-file-list="false"
                   :on-success="handleUploadSuccess">
          <img v-if="imageUrl" :src="imageUrl" class="avatar" />
          <el-icon v-else class="avatar-uploader-icon">
            <Plus />
          </el-icon>
        </el-upload>
      </el-card>

      <div class="result-grid" v-if="result">
        <el-card class="panel">
          <template #header>统计</template>
          <div class="stats">
            <div class="stat-item" v-for="(v,k) in result.counts" :key="k">
              <span class="k">{{ k }}</span>
              <span class="v">{{ v }}</span>
            </div>
            <div class="stat-item">
              <span class="k">head</span>
              <span class="v">{{ result.head }}</span>
            </div>
          </div>
        </el-card>
        <el-card class="panel" v-if="analysisMarkdown">
          <template #header>AI 分析</template>
          <div class="markdown" v-html="analysisMarkdown"></div>
        </el-card>
        <el-card class="panel" v-if="analysisImageUrl">
          <template #header>可视化</template>
          <img :src="analysisImageUrl" style="width: 100%; max-height: 520px; object-fit: contain;" />
        </el-card>
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
const conf = ref(25);
const behaviorWeight = ref('');
const countsWeight = ref('');
const preferManualAnalysis = ref(false);
const manualAnalysisJsonPath = ref('');
const state = reactive({
  img: '',
  weight_items: [] as any[],
});

const behaviorWeightItems = computed(() => state.weight_items.filter(w => /student|behavior|best/i.test(w.value)));
const countsWeightItems = computed(() => state.weight_items.filter(w => /count|head|per_counts/i.test(w.value)));

const formatTooltip = (val: number) => (val / 100);

const handleUploadSuccess: UploadProps['onSuccess'] = (response, file) => {
  imageUrl.value = URL.createObjectURL(file.raw!);
  state.img = response.data; // Spring 返回的文件访问 URL
};

const getWeights = () => {
  // 直接走 Vite 代理到 Flask 5000
  request.get('/flask/file_names')
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
          const cand = items.find((x:any) => /student|behavior/i.test(x.value)) || items.find((x:any) => /best_student/i.test(x.value));
          if (cand) behaviorWeight.value = cand.value;
        }
        if (!countsWeight.value) {
          const cand = items.find((x:any) => /count|head|per_counts/i.test(x.value)) || items.find((x:any) => /best_per_counts/i.test(x.value));
          if (cand) countsWeight.value = cand.value;
        }
      } catch (e:any) {
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
    conf: (conf.value / 100),
    imgsz: 640,
    backend: wantOrt ? 'onnxruntime' : undefined,
    save_json: true,
  };
  request.post('/flask/dualDetect', payload).then((res) => {
    if (res.status === 200) {
      result.value = res;
      savedBehaviorPath.value = res?.saved_paths?.behavior_json || '';
      ElMessage.success('检测完成');
    } else {
      ElMessage.error(res.message || '检测失败');
    }
  }).catch((e) => ElMessage.error(String(e)));
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
    return request.post('/flask/analyze', payloadReuseDirect).then((res) => {
      if (res.status === 200) {
        analysisMarkdown.value = res.analysis_markdown || '';
        analysisJson.value = res.analysis_json || null;
        analysisImageUrl.value = res.analysis_image_url || '';
        savedAnalysisJsonPath.value = res.saved_analysis_json_path || manualAnalysisJsonPath.value;
        ElMessage.success('分析完成(使用指定AI化JSON)');
      } else {
        ElMessage.error(res.message || '分析失败');
      }
    }).catch((e) => ElMessage.error(String(e)));
  }
  // 若已有已AI化的 JSON，优先直接复用，避免重复调用模型
  if (savedAnalysisJsonPath.value) {
    const payloadReuse: any = {
      analysis_json_path: savedAnalysisJsonPath.value,
      title: '课堂行为分析',
    };
    return request.post('/flask/analyze', payloadReuse).then((res) => {
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
    }).catch((e) => ElMessage.error(String(e)));
  }
  // 若尚未运行双模型检测，则先跑一遍保证严格流程
  const ensureDual = () => {
    if (savedBehaviorPath.value) return Promise.resolve({ ok: true });
    const payloadDual = {
      inputImg: state.img,
      behavior_weight: behaviorWeight.value || './weights/best_student.pt',
      counts_weight: countsWeight.value || './weights/best_per_counts.pt',
      conf: (conf.value / 100),
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

  ensureDual().then(() => {
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
    } catch (e) { /* ignore */ }

    request.post('/flask/analyze', payload).then((res) => {
      if (res.status === 200) {
        analysisMarkdown.value = res.analysis_markdown || '';
        analysisJson.value = res.analysis_json || null;
        analysisImageUrl.value = res.analysis_image_url || '';
        savedAnalysisJsonPath.value = res.saved_analysis_json_path || '';
        ElMessage.success('分析完成');
      } else {
        ElMessage.error(res.message || '分析失败');
      }
    }).catch((e) => ElMessage.error(String(e)));
  }).catch((e:any) => ElMessage.error(String(e)));
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
.header {
  width: 100%;
  display: flex;
  align-items: center;
}
.conf-label { font-size: 14px; color: #909399; margin-right: 10px; }
.card {
  width: 100%;
  height: 520px;
  border-radius: 10px;
  margin-top: 12px;
  display: flex;
  justify-content: center;
  align-items: center;
}
.avatar-uploader .avatar {
  width: 100%;
  height: 480px;
  object-fit: contain;
  display: block;
}
.avatar-uploader-icon { font-size: 28px; color: #8c939d; width: 100%; height: 480px; text-align: center; }
.result-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 12px;
}
.panel { min-height: 200px; }
.stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}
.stat-item { display: flex; justify-content: space-between; padding: 6px 8px; background: #f7f7f7; border-radius: 6px; }
.k { color: #666; }
.v { font-weight: 600; }
.markdown { white-space: pre-wrap; line-height: 1.6; }
</style>