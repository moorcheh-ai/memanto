// 测试脚本
const sortByStringLength = require('./sortByStringLength');

// 测试用例
function runTests() {
    console.log('测试 1: 正常字符串数组');
    const arr1 = ['apple', 'banana', 'kiwi', 'strawberry'];
    const sorted1 = sortByStringLength(arr1);
    console.log('输入:', arr1);
    console.log('输出:', sorted1);
    console.log('预期: ["kiwi", "apple", "banana", "strawberry"]');
    console.log('结果:', JSON.stringify(sorted1) === JSON.stringify(['kiwi', 'apple', 'banana', 'strawberry']) ? '通过' : '失败');

    console.log('\n测试 2: 空数组');
    const arr2 = [];
    const sorted2 = sortByStringLength(arr2);
    console.log('输入:', arr2);
    console.log('输出:', sorted2);
    console.log('预期: []');
    console.log('结果:', sorted2.length === 0 ? '通过' : '失败');

    console.log('\n测试 3: 包含相同长度的字符串');
    const arr3 = ['cat', 'dog', 'bird'];
    const sorted3 = sortByStringLength(arr3);
    console.log('输入:', arr3);
    console.log('输出:', sorted3);
    console.log('预期: ["cat", "dog", "bird"] (长度相同，保持原顺序)');
    console.log('结果:', JSON.stringify(sorted3) === JSON.stringify(['cat', 'dog', 'bird']) ? '通过' : '失败');

    console.log('\n测试 4: 输入不是数组');
    try {
        sortByStringLength('not an array');
        console.log('结果: 失败 - 未抛出错误');
    } catch (e) {
        console.log('结果: 通过 - 错误信息:', e.message);
    }

    console.log('\n测试 5: 数组包含非字符串元素');
    try {
        sortByStringLength(['hello', 123, 'world']);
        console.log('结果: 失败 - 未抛出错误');
    } catch (e) {
        console.log('结果: 通过 - 错误信息:', e.message);
    }

    console.log('\n测试 6: 原数组未被修改');
    const arr6 = ['b', 'aaa', 'cc'];
    const sorted6 = sortByStringLength(arr6);
    console.log('原数组:', arr6);
    console.log('排序后:', sorted6);
    console.log('原数组是否改变:', JSON.stringify(arr6) === JSON.stringify(['b', 'aaa', 'cc']) ? '未改变' : '已改变');
}

runTests();