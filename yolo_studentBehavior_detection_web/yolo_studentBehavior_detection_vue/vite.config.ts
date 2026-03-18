import vue from '@vitejs/plugin-vue';
import { resolve } from 'path';
import { defineConfig, loadEnv, ConfigEnv } from 'vite';
import vueSetupExtend from 'vite-plugin-vue-setup-extend';

// 临时静音 Dart Sass legacy-js-api 弃用警告（仅开发态）
// 更激进的静音方案：同时拦截 Vite logger、console.warn 以及 process.stderr.write
// 说明：仅用于开发阶段；构建阶段仍保留原始输出，方便 CI 发现问题。
function suppressLegacySassWarning() {
	const KEYWORD = 'legacy-js-api';
	return {
		name: 'suppress-legacy-sass-warning',
		apply: 'serve',
		configResolved(config: any) {
			const origWarn = config.logger.warn.bind(config.logger);
			config.logger.warn = (msg: any, options?: any) => {
				if (typeof msg === 'string' && msg.includes(KEYWORD)) return;
				origWarn(msg, options);
			};
		},
		configureServer() {
			const origConsoleWarn = console.warn;
			// 拦截 console.warn
			console.warn = (...args: any[]) => {
				if (args.some(a => typeof a === 'string' && a.includes(KEYWORD))) return;
				origConsoleWarn(...args);
			};
			// 拦截底层 stderr 写入（部分依赖直接写入 process.stderr）
			const origStderrWrite = process.stderr.write.bind(process.stderr);
			process.stderr.write = (chunk: any, encoding?: any, cb?: any) => {
				if (typeof chunk === 'string' && chunk.includes(KEYWORD)) {
					return true; // 吞掉该行
				}
				return origStderrWrite(chunk, encoding as any, cb);
			};
		}
	} as any;
}

const pathResolve = (dir: string) => {
	return resolve(__dirname, '.', dir);
};

const alias: Record<string, string> = {
	'/@': pathResolve('./src/'),
	'vue-i18n': 'vue-i18n/dist/vue-i18n.cjs.js',
};

const viteConfig = defineConfig((mode: ConfigEnv) => {
	const env = loadEnv(mode.mode, process.cwd());
	return {
		plugins: [vue(), vueSetupExtend(), suppressLegacySassWarning()],
		root: process.cwd(),
		resolve: { alias },
		base: mode.command === 'serve' ? './' : env.VITE_PUBLIC_PATH,
		optimizeDeps: {
			include: ['element-plus/es/locale/lang/zh-cn', 'element-plus/es/locale/lang/en', 'element-plus/es/locale/lang/zh-tw'],
		},
		server: {
			host: '0.0.0.0',
			port: env.VITE_PORT as unknown as number,
			open: env.VITE_OPEN,
			hmr: { overlay: false },
			proxy: {
				'/api': {
					//设置拦截器  拦截器格式   斜杠+拦截器名字，名字可以自己定
					target: 'http://localhost:9999/', //代理的目标地址
					ws: true,
					changeOrigin: true,
					rewrite: (path) => path.replace(/^\/api/, ''),
				},
				'/flask': {
					//设置拦截器  拦截器格式   斜杠+拦截器名字，名字可以自己定
					target: 'http://localhost:5000/', //代理的目标地址
					ws: true,
					changeOrigin: true,
					rewrite: (path) => path.replace(/^\/flask/, ''),
				},
			},
		},
		build: {
			outDir: 'dist',
			chunkSizeWarningLimit: 1500,
			rollupOptions: {
				output: {
					entryFileNames: `assets/[name].[hash].js`,
					chunkFileNames: `assets/[name].[hash].js`,
					assetFileNames: `assets/[name].[hash].[ext]`,
					compact: true,
					manualChunks: {
						vue: ['vue', 'vue-router', 'pinia'],
						echarts: ['echarts'],
					},
				},
			},
		},
		css: { preprocessorOptions: { css: { charset: false } } },
		define: {
			__VUE_I18N_LEGACY_API__: JSON.stringify(false),
			__VUE_I18N_FULL_INSTALL__: JSON.stringify(false),
			__INTLIFY_PROD_DEVTOOLS__: JSON.stringify(false),
			__VERSION__: JSON.stringify(process.env.npm_package_version),
		},
	};
});

export default viteConfig;
