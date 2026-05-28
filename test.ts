// 测试脚本
import { get, parsePath } from './get';

// 测试 parsePath
console.assert(
    JSON.stringify(parsePath('a.b[0].c')) === JSON.stringify(['a', 'b', 0, 'c']),
    'parsePath should parse correctly'
);
console.assert(
    JSON.stringify(parsePath('a')) === JSON.stringify(['a']),
    'parsePath should handle single key'
);
console.assert(
    JSON.stringify(parsePath('[0]')) === JSON.stringify([0]),
    'parsePath should handle array index'
);

// 测试 get
const obj = {
    a: {
        b: [
            { c: 'value' }
        ]
    }
};

console.assert(get(obj, 'a.b[0].c') === 'value', 'get should retrieve nested value');
console.assert(get(obj, 'a.b[1].c') === undefined, 'get should return undefined for missing path');
console.assert(get(obj, 'a.b[0].c', 'default') === 'value', 'get should ignore default when value exists');
console.assert(get(obj, 'x.y', 'default') === 'default', 'get should return default for missing path');
console.assert(get(null, 'a') === undefined, 'get should handle null object');
console.assert(get(undefined, 'a', 'default') === 'default', 'get should handle undefined object');

console.log('All tests passed!');
