// 实现一个类型工具，将联合类型转换为交叉类型
// 例如：UnionToIntersection<'a' | 'b'> 应得到 'a' & 'b'

// 核心思路：利用函数参数逆变位置，通过条件类型推断将联合类型转换为交叉类型
// 参考：https://www.typescriptlang.org/docs/handbook/2/conditional-types.html

type UnionToIntersection<U> = 
  (U extends any ? (k: U) => void : never) extends (k: infer I) => void ? I : never;

// 测试用例
// 基本类型
type Test1 = UnionToIntersection<'a' | 'b'>; // 'a' & 'b'
type Test2 = UnionToIntersection<string | number>; // string & number (never)
type Test3 = UnionToIntersection<{ a: 1 } | { b: 2 }>; // { a: 1 } & { b: 2 }

// 辅助函数：检查类型是否相等（用于测试）
type Equal<X, Y> = (<T>() => T extends X ? 1 : 2) extends <T>() => T extends Y ? 1 : 2 ? true : false;

// 导出以便测试
export { UnionToIntersection, Equal };