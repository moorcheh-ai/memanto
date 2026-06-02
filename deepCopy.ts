// 主代码：实现一个类型安全的深拷贝函数
// 支持对象、数组、基本类型、Date、Map、Set等

type DeepCopy<T> = T extends Date
  ? Date
  : T extends Map<infer K, infer V>
  ? Map<DeepCopy<K>, DeepCopy<V>>
  : T extends Set<infer U>
  ? Set<DeepCopy<U>>
  : T extends Array<infer U>
  ? Array<DeepCopy<U>>
  : T extends object
  ? { [K in keyof T]: DeepCopy<T[K]> }
  : T;

function deepCopy<T>(value: T): DeepCopy<T> {
  if (value === null || typeof value !== 'object') {
    return value as DeepCopy<T>;
  }

  if (value instanceof Date) {
    return new Date(value.getTime()) as DeepCopy<T>;
  }

  if (value instanceof Map) {
    const map = new Map();
    value.forEach((v, k) => {
      map.set(deepCopy(k), deepCopy(v));
    });
    return map as DeepCopy<T>;
  }

  if (value instanceof Set) {
    const set = new Set();
    value.forEach((v) => {
      set.add(deepCopy(v));
    });
    return set as DeepCopy<T>;
  }

  if (Array.isArray(value)) {
    return value.map((item) => deepCopy(item)) as DeepCopy<T>;
  }

  // 处理普通对象
  const result: Record<string, any> = {};
  for (const key in value) {
    if (Object.prototype.hasOwnProperty.call(value, key)) {
      result[key] = deepCopy((value as any)[key]);
    }
  }
  return result as DeepCopy<T>;
}

export { deepCopy, DeepCopy };
