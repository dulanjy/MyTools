<template>
	<div class="behavior-bi-container">
		<el-row :gutter="20">
			<el-col :span="24">
				<el-card shadow="hover" class="mb15">
					<template #header>
						<span>学生行为分析概览</span>
					</template>
					<div style="height: 300px" ref="trendChartRef"></div>
				</el-card>
			</el-col>
		</el-row>

		<el-row :gutter="20">
			<el-col :span="12">
				<el-card shadow="hover">
					<template #header>
						<span>不良行为占比</span>
					</template>
					<div style="height: 300px" ref="pieChartRef"></div>
				</el-card>
			</el-col>
			<el-col :span="12">
				<el-card shadow="hover">
					<template #header>
						<span>专注度分布</span>
					</template>
					<div style="height: 300px" ref="barChartRef"></div>
				</el-card>
			</el-col>
		</el-row>
	</div>
</template>

<script lang="ts">
import { defineComponent, nextTick, onMounted, ref } from 'vue';
import * as echarts from 'echarts';
import request from '/@/utils/request';

export default defineComponent({
	name: 'BehaviorBi',
	setup() {
		const trendChartRef = ref<HTMLElement | null>(null);
		const pieChartRef = ref<HTMLElement | null>(null);
		const barChartRef = ref<HTMLElement | null>(null);

		const initCharts = (data: any[]) => {
			if (!data || data.length === 0) return;

			const trendChart = echarts.init(trendChartRef.value!);
			const dates = data.map((item) => new Date(item.recordTime).toLocaleDateString());
			const focusScores = data.map((item) => item.focusScore || 0);

			const getCount = (item: any, rateKey: string) => {
				try {
					const metrics = JSON.parse(item.metricsJson || '{}');
					const rate = metrics[rateKey] || 0;
					return Math.round((item.studentCount || 0) * rate / 100);
				} catch {
					return 0;
				}
			};

			const bowHeadCounts = data.map((item) => getCount(item, 'head_down_rate'));

			trendChart.setOption({
				title: { text: '专注度与低头人数趋势' },
				tooltip: { trigger: 'axis' },
				legend: { data: ['专注度评分', '低头人数'] },
				xAxis: { type: 'category', data: dates },
				yAxis: [
					{ type: 'value', name: '评分', max: 100 },
					{ type: 'value', name: '人数' },
				],
				series: [
					{ name: '专注度评分', type: 'line', data: focusScores, yAxisIndex: 0, smooth: true },
					{ name: '低头人数', type: 'bar', data: bowHeadCounts, yAxisIndex: 1 },
				],
			});

			const latest = data[data.length - 1];
			const latestMetrics = JSON.parse(latest.metricsJson || '{}');
			const latestStudentCount = latest.studentCount || 0;

			const bowCount = Math.round(latestStudentCount * (latestMetrics.head_down_rate || 0) / 100);
			const phoneCount = Math.round(latestStudentCount * (latestMetrics.phone_usage_rate || 0) / 100);
			const sleepCount = Math.round(latestStudentCount * (latestMetrics.sleeping_rate || 0) / 100);
			const normalCount = Math.max(0, latestStudentCount - bowCount - phoneCount - sleepCount);

			const pieChart = echarts.init(pieChartRef.value!);
			pieChart.setOption({
				title: { text: '最新课堂行为分布', subtext: new Date(latest.recordTime).toLocaleString() },
				tooltip: { trigger: 'item' },
				series: [
					{
						name: '行为',
						type: 'pie',
						radius: '50%',
						data: [
							{ value: bowCount, name: '低头' },
							{ value: phoneCount, name: '玩手机' },
							{ value: sleepCount, name: '睡觉' },
							{ value: normalCount, name: '正常听讲' },
						],
					},
				],
			});

			const barChart = echarts.init(barChartRef.value!);
			const scoreRanges: Record<string, number> = { '0-60': 0, '60-80': 0, '80-100': 0 };
			data.forEach((d) => {
				if ((d.focusScore || 0) < 60) scoreRanges['0-60']++;
				else if ((d.focusScore || 0) < 80) scoreRanges['60-80']++;
				else scoreRanges['80-100']++;
			});

			barChart.setOption({
				title: { text: '历史专注度区间统计' },
				tooltip: { trigger: 'axis' },
				xAxis: { type: 'category', data: Object.keys(scoreRanges) },
				yAxis: { type: 'value' },
				series: [{ type: 'bar', data: Object.values(scoreRanges) }],
			});

			window.addEventListener('resize', () => {
				trendChart.resize();
				pieChart.resize();
				barChart.resize();
			});
		};

		const fetchData = async () => {
			try {
				const res = await request.get('/api/behavior/stats');
				if (res.code == 0) {
					initCharts(res.data || []);
				}
			} catch (error) {
				console.error('Failed to fetch behavior stats:', error);
			}
		};

		onMounted(() => {
			nextTick(() => {
				fetchData();
			});
		});

		return {
			trendChartRef,
			pieChartRef,
			barChartRef,
		};
	},
});
</script>

<style scoped>
.behavior-bi-container {
	padding: 15px;
}
.mb15 {
	margin-bottom: 15px;
}
</style>
