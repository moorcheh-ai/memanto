// 测试代码
import { toUpperCaseArray } from './main';

function test() {
    // 测试正常情况
    const result = toUpperCaseArray(['hello', 'world']);
    console.assert(result[0] === 'HELLO', '第一个元素应为HELLO');
    console.assert(result[1] === 'WORLD', '第二个元素应为WORLD');

    // 测试空数组
    try {
        toUpperCaseArray([]);
        console.error('空数组应抛出错误');
    } catch (e) {
        console.log('空数组测试通过');
    }

    console.log('所有测试通过');
}

test();
