# 🎨 样式优化快速参考

## 📌 核心改动要点

### 1️⃣ 新增主题文件
```
src/theme/light-tech.scss (365 行)
├── CSS 变量定义 (颜色、阴影、过渡)
├── 布局优化 (.layout-container)
├── 菜单样式 (.el-menu)
├── 卡片增强 (.el-card)
├── 按钮美化 (.el-button)
├── 输入框优化 (.el-input)
├── 表格样式 (.el-table)
└── 其他组件调整
```

### 2️⃣ 全局样式更新
```scss
/* app.scss 更新 */
- 背景色：#f8f8f8 → #f8f9fa
- 字体族：系统默认堆栈
- 侧栏：渐变背景 + 精致边框
- 顶栏：渐变 + 底部阴影
```

### 3️⃣ 页面布局重构

#### 行为预测 (behaviorPredict)
```
变化：
✓ 控制栏 → Grid 布局 (auto-fit)
✓ 按钮栏 → Flex 换行
✓ 上传区 → 渐变背景
✓ 结果区 → Row/Col 响应式网格
✓ 空状态 → 新增提示图标
```

#### 图像预测 (imgPredict)
```
变化：
✓ 控制面板 → Grid 4 列布局
✓ 内容区 → 2 列 (平板 1 列)
✓ 上传区 → 优雅的拖拽样式
✓ 结果卡片 → 分项展示
✓ 进度条 → 新增置信度可视化
```

---

## 🎨 CSS 变量速查表

### 颜色系统
```scss
// 主色系
--tech-primary:           #0066ff  // 科技蓝
--tech-primary-light:     #e6f2ff  // 浅蓝
--tech-primary-lighter:   #f2f9ff  // 极浅蓝
--tech-accent:            #00d4ff  // 活力青
--tech-accent-light:      #e0f7ff  // 浅青

// 中性色
--tech-white:             #ffffff
--tech-gray-50:           #f8f9fa
--tech-gray-100:          #f1f3f5
--tech-gray-200:          #e9ecef
--tech-gray-300:          #dee2e6
--tech-gray-400:          #ced4da
--tech-gray-500:          #adb5bd
--tech-gray-600:          #868e96
--tech-gray-700:          #495057
--tech-gray-800:          #343a40
--tech-gray-900:          #212529

// 功能色
--tech-success:           #52c41a
--tech-warning:           #faad14
--tech-danger:            #ff4d4f
--tech-info:              #1890ff
```

### 背景与边框
```scss
--tech-bg-primary:        #ffffff
--tech-bg-secondary:      #f8f9fa
--tech-bg-tertiary:       #f1f3f5
--tech-border-color:      #e9ecef
--tech-border-color-light: #f1f3f5
--tech-divider-color:     #dee2e6
```

### 文本
```scss
--tech-text-primary:      #212529
--tech-text-secondary:    #495057
--tech-text-tertiary:     #868e96
--tech-text-placeholder:  #adb5bd
```

### 效果
```scss
--tech-shadow-sm:    0 2px 8px rgba(0, 0, 0, 0.06)
--tech-shadow-md:    0 4px 16px rgba(0, 0, 0, 0.08)
--tech-shadow-lg:    0 8px 24px rgba(0, 0, 0, 0.1)
--tech-shadow-focus: 0 0 0 3px rgba(0, 102, 255, 0.1)

--tech-transition-fast:   150ms cubic-bezier(0.4, 0, 0.2, 1)
--tech-transition-base:   200ms cubic-bezier(0.4, 0, 0.2, 1)
--tech-transition-slow:   300ms cubic-bezier(0.4, 0, 0.2, 1)
```

---

## 🔧 常见定制

### 修改主色
```scss
// light-tech.scss :root 中
--tech-primary: #0066ff;          // 改为你的颜色
--tech-primary-light: #e6f2ff;    // 自动计算浅色
--tech-primary-lighter: #f2f9ff;  // 自动计算极浅色
```

### 调整圆角
```scss
// behaviorPredict/index.vue
.control-bar {
  border-radius: 12px;  // 改为 8px 或 16px
}
```

### 改变间距
```scss
.behavior-view {
  gap: 20px;  // 改为 16px 或 24px
  padding: 24px;  // 改为 16px 或 32px
}
```

---

## 📱 响应式断点

```scss
// 平板 (768px - 1024px)
@media (max-width: 1024px) {
  .control-panel {
    grid-template-columns: 1fr 1fr;
  }
  .content-area {
    grid-template-columns: 1fr;  // 改成 1 列
  }
}

// 手机 (< 768px)
@media (max-width: 768px) {
  .behavior-view {
    padding: 16px !important;     // 减少内边距
  }
  .control-bar {
    grid-template-columns: 1fr;   // 改成 1 列
  }
}
```

---

## 🚀 性能优化技巧

### 1. 使用 CSS 变量替代硬编码
```scss
// ❌ 不好
.card { color: #0066ff; }

// ✅ 好
.card { color: var(--tech-primary); }
```

### 2. 复用阴影
```scss
// ❌ 不好
box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);

// ✅ 好
box-shadow: var(--tech-shadow-sm);
```

### 3. 统一过渡时间
```scss
// ❌ 不好
transition: all 150ms ease;

// ✅ 好
transition: all var(--tech-transition-fast);
```

---

## 📋 检查清单

部署前检查：
- [ ] 检查浏览器兼容性 (Chrome/Firefox/Safari/Edge)
- [ ] 验证深色模式支持
- [ ] 测试移动端响应式
- [ ] 检查性能 (LightHouse)
- [ ] 验证无障碍等级 (A11y)
- [ ] 测试打印样式
- [ ] 检查国际化文本换行

---

## 🎯 最佳实践

### ✅ DO
- 使用 CSS 变量
- 遵循 8px 网格系统
- 使用预定义的颜色和阴影
- 响应式优先设计
- 添加合理的过渡效果

### ❌ DON'T
- 硬编码颜色值
- 使用 !important
- 过度使用阴影
- 忽视移动端设计
- 添加过多动画

---

**提示**：所有样式都已按照现代设计系统组织，易于维护和扩展！🎉
