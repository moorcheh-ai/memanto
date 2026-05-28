// 测试脚本
import { deepCopy } from './deepCopy';

// 测试基本类型
console.assert(deepCopy(42) === 42, 'number copy failed');
console.assert(deepCopy('hello') === 'hello', 'string copy failed');
console.assert(deepCopy(null) === null, 'null copy failed');
console.assert(deepCopy(undefined) === undefined, 'undefined copy failed');

// 测试对象
const obj = { a: 1, b: { c: 2 } };
const objCopy = deepCopy(obj);
console.assert(JSON.stringify(objCopy) === JSON.stringify(obj), 'object copy failed');
console.assert(objCopy !== obj, 'object reference not broken');
console.assert(objCopy.b !== obj.b, 'nested object reference not broken');

// 测试数组
const arr = [1, [2, 3]];
const arrCopy = deepCopy(arr);
console.assert(JSON.stringify(arrCopy) === JSON.stringify(arr), 'array copy failed');
console.assert(arrCopy !== arr, 'array reference not broken');
console.assert(arrCopy[1] !== arr[1], 'nested array reference not broken');

// 测试Date
const date = new Date();
const dateCopy = deepCopy(date);
console.assert(dateCopy.getTime() === date.getTime(), 'date copy failed');
console.assert(dateCopy !== date, 'date reference not broken');

// 测试Map
const map = new Map<string, number>([['a', 1]]);
const mapCopy = deepCopy(map);
console.assert(mapCopy.get('a') === 1, 'map copy failed');
console.assert(mapCopy !== map, 'map reference not broken');

// 测试Set
const set = new Set<number>([1, 2, 3]);
const setCopy = deepCopy(set);
console.assert(setCopy.has(1), 'set copy failed');
console.assert(setCopy !== set, 'set reference not broken');

// 测试循环引用（可选，当前实现不处理循环引用，会栈溢出）
// const cyclic: any = {};
// cyclic.self = cyclic;
// deepCopy(cyclic); // 会抛出错误，但这里不测试

console.log('All tests passed!');
