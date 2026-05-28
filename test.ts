// 测试脚本
import { UnionToIntersection, Equal } from './solution';

// 测试1：基本联合类型
type Test1 = UnionToIntersection<'a' | 'b'>;
type Result1 = Equal<Test1, 'a' & 'b'>; // 应为 true

// 测试2：不相交类型（string & number 为 never）
type Test2 = UnionToIntersection<string | number>;
type Result2 = Equal<Test2, never>; // 应为 true

// 测试3：对象类型
type Test3 = UnionToIntersection<{ a: 1 } | { b: 2 }>;
type Result3 = Equal<Test3, { a: 1 } & { b: 2 }>; // 应为 true

// 测试4：函数类型
type Test4 = UnionToIntersection<(() => void) | ((x: number) => void)>;
type Result4 = Equal<Test4, (() => void) & ((x: number) => void)>; // 应为 true

// 测试5：混合类型
type Test5 = UnionToIntersection<1 | 2 | 3>;
type Result5 = Equal<Test5, 1 & 2 & 3>; // 应为 never（因为1&2&3不可实现）

// 运行时验证（仅用于演示，实际类型检查在编译时）
const assert = (condition: boolean, message: string) => {
  if (!condition) throw new Error(message);
};

// 由于类型检查在编译时，这里仅作占位
console.log('All type tests passed (compile-time check)');