// 主挑战代码：实现一个函数，接收一个字符串数组，返回按字符串长度排序后的新数组
// 如果输入不是数组或包含非字符串元素，抛出错误

/**
 * 按字符串长度对数组进行排序
 * @param {string[]} arr - 字符串数组
 * @returns {string[]} 按长度升序排列的新数组
 * @throws {Error} 如果输入不是数组或包含非字符串元素
 */
function sortByStringLength(arr) {
    // 检查输入是否为数组
    if (!Array.isArray(arr)) {
        throw new Error('输入必须是一个数组');
    }

    // 检查数组中的每个元素是否为字符串
    for (let i = 0; i < arr.length; i++) {
        if (typeof arr[i] !== 'string') {
            throw new Error(`数组索引 ${i} 的元素不是字符串`);
        }
    }

    // 返回按长度排序的新数组（不修改原数组）
    return arr.slice().sort((a, b) => a.length - b.length);
}

// 导出函数以便测试
if (typeof module !== 'undefined' && module.exports) {
    module.exports = sortByStringLength;
}