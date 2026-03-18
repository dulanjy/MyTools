export type StudentKind = 'student' | 'head' | '';

export const STUDENT_KIND_ITEMS = [
	{ value: 'student', label: '行为识别' },
	{ value: 'head', label: '人数统计' },
];

const STUDENT_WEIGHT_KEYWORDS = ['student', 'behavior', 'classroom', 'best_student'];
const HEAD_WEIGHT_KEYWORDS = ['head', 'count', 'counts', 'per_counts', 'best_per_counts'];
const LEGACY_CROP_KEYWORDS = ['corn', 'maize', 'rice', 'paddy', 'strawberry', 'tomato'];

function containsAny(source: string, keys: string[]): boolean {
	return keys.some((k) => source.includes(k));
}

export function inferKindFromWeight(weight: string): StudentKind {
	if (!weight) return '';
	const v = String(weight).toLowerCase();
	if (containsAny(v, HEAD_WEIGHT_KEYWORDS)) return 'head';
	if (containsAny(v, STUDENT_WEIGHT_KEYWORDS) || containsAny(v, LEGACY_CROP_KEYWORDS)) return 'student';
	return '';
}

export function normalizeKind(kind: string): StudentKind {
	const k = String(kind || '').toLowerCase();
	if (!k) return '';
	if (k === 'head') return 'head';
	if (k === 'student' || k === 'behavior' || k === 'classroom') return 'student';
	if (containsAny(k, LEGACY_CROP_KEYWORDS)) return 'student';
	return '';
}

export function filterWeightsByKind<T extends { value?: string }>(items: T[], kind: string): T[] {
	const normalized = normalizeKind(kind);
	if (!Array.isArray(items)) return [];

	const studentOrHeadOnly = items.filter((item) => {
		const v = String(item?.value || '').toLowerCase();
		return containsAny(v, STUDENT_WEIGHT_KEYWORDS) || containsAny(v, HEAD_WEIGHT_KEYWORDS);
	});
	const candidatePool = studentOrHeadOnly.length ? studentOrHeadOnly : items;

	if (!normalized) return candidatePool;
	if (normalized === 'head') {
		const headOnly = candidatePool.filter((item) => containsAny(String(item?.value || '').toLowerCase(), HEAD_WEIGHT_KEYWORDS));
		return headOnly.length ? headOnly : candidatePool;
	}
	const studentOnly = candidatePool.filter((item) => {
		const v = String(item?.value || '').toLowerCase();
		return containsAny(v, STUDENT_WEIGHT_KEYWORDS) || containsAny(v, LEGACY_CROP_KEYWORDS);
	});
	return studentOnly.length ? studentOnly : candidatePool;
}
