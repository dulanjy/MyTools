import vue from '@vitejs/plugin-vue';
import { resolve } from 'path';
import { defineConfig, loadEnv, ConfigEnv } from 'vite';
import vueSetupExtend from 'vite-plugin-vue-setup-extend';

// 涓存椂闈欓煶 Dart Sass legacy-js-api 寮冪敤璀﹀憡锛堜粎寮€鍙戞€侊級
// 鏇存縺杩涚殑闈欓煶鏂规锛氬悓鏃舵嫤鎴?Vite logger銆乧onsole.warn 浠ュ強 process.stderr.write
// 璇存槑锛氫粎鐢ㄤ簬寮€鍙戦樁娈碉紱鏋勫缓闃舵浠嶄繚鐣欏師濮嬭緭鍑猴紝鏂逛究 CI 鍙戠幇闂銆?
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
			// 鎷︽埅 console.warn
			console.warn = (...args: any[]) => {
				if (args.some(a => typeof a === 'string' && a.includes(KEYWORD))) return;
				origConsoleWarn(...args);
			};
			// 鎷︽埅搴曞眰 stderr 鍐欏叆锛堥儴鍒嗕緷璧栫洿鎺ュ啓鍏?process.stderr锛?
			const origStderrWrite = process.stderr.write.bind(process.stderr);
			process.stderr.write = (chunk: any, encoding?: any, cb?: any) => {
				if (typeof chunk === 'string' && chunk.includes(KEYWORD)) {
					return true; // 鍚炴帀璇ヨ
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

const normalizeProxyTarget = (raw: string | undefined, fallback: string): string => {
	const value = (raw ?? '').trim().replace(/^['"]|['"]$/g, '');
	if (!value) return fallback;
	if (/^https?:\/\//i.test(value)) return value;
	// Accept bare host:port and normalize to http URL.
	if (/^[\w.-]+(?::\d+)?(?:\/.*)?$/i.test(value)) return `http://${value}`;
	return fallback;
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
					// Proxy API requests to Spring Boot backend.
					target: normalizeProxyTarget(env.VITE_SPRING_BASE_URL, 'http://localhost:9999/'),
					ws: true,
					changeOrigin: true,
					rewrite: (path) => path.replace(/^\/api/, ''),
				},
				'/flask': {
					// Proxy Flask requests to Python backend.
					target: normalizeProxyTarget(env.VITE_FLASK_BASE_URL, 'http://localhost:5000/'),
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

